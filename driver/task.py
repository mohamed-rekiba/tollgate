"""The task loop: plan, plan review, approval, plan tag, then each ticket in order.

    PYTHONPATH=<tollgate> python3 -m driver.task --project . --task retries --request-file r.txt

The task's own log is .tollgate/logs/task-<task id>.jsonl. Each ticket keeps its
own log. A task that starts again repeats no finished step. A ticket that waits
for the advisor or is parked does not stop the others: the report says why.

Exit codes: 0 every ticket has a pull request, 3 something waits for the advisor,
4 another driver holds the task, 1 an error.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from action import plan as pl
from action import settings as st
from action import tickets as tk
from driver import advisor, report, roles
from driver.driver import Busy, Driver, Parked, TicketLock, git, push
from driver.log import Log, read

PLAN_LENSES = ("simplicity", "fresh_reader", "readiness")
MAX_ROUNDS = 4
OPEN_LEVELS = ("blocking", "major")


class Task:
    def __init__(self, project: str, task_id: str, request: str, server, base="origin/main"):
        if not pl.ID.match(task_id):
            raise pl.PlanError(f"not a valid task id: {task_id!r}")
        self.project = os.path.abspath(project)
        self.id = task_id
        self.request = request
        self.server = server
        self.base = base
        self.logs = os.path.join(self.project, ".tollgate", "logs")
        self.log_path = os.path.join(self.logs, f"task-{task_id}.jsonl")
        self.ai_decisions = 0

    def role(self, name, inputs, lens=None, command=None):
        s = self.settings
        command = command or (s["ai"]["reviewer"] if name == "reviewer" else s["ai"]["builder"])
        answer = roles.run(command, name, inputs, self.copy, s["stop"]["attempt_minutes"], lens,
                           s["sandbox"], s["container_image"])
        return answer

    def read_copy(self, path):
        p = Path(self.copy, path)
        return p.read_text() if p.exists() else None

    def check_plan(self) -> list:
        text = self.read_copy(pl.plan_path(self.id))
        if text is None:
            return [f"{pl.plan_path(self.id)} was not written"]
        try:
            plan = pl.parse(text)
        except pl.PlanError as err:
            return [str(err)]
        if plan.id != self.id:
            return [f"the plan names {plan.id}, not {self.id}"]
        used = [t for t in plan.tickets
                if git(self.copy, "tag", "--list", f"tg/freeze/{t}/*") and not Path(
                    self.logs, f"{t}.jsonl").exists()]
        problems = [f"ticket id {t} is already used by an earlier freeze; pick a new id"
                    for t in used]
        return problems + pl.check_tickets(plan, self.read_copy)

    # Steps.

    def write_plan(self, problems=None, hint=""):
        answer = self.role("builder", {"mode": "plan", "task_id": self.id, "request": self.request,
                                       "problems": problems or [], "hint": hint})
        self.log.add("plan_written", cost_usd=answer.cost_usd)
        for _ in range(2):
            problems = self.check_plan()
            if not problems:
                return
            self.log.add("plan_invalid", problems=problems)
            answer = self.role("builder", {"mode": "plan", "task_id": self.id,
                                           "request": self.request, "problems": problems})
            self.log.add("plan_written", cost_usd=answer.cost_usd)
        problems = self.check_plan()
        if problems:
            raise pl.PlanError("; ".join(problems))

    def review_plan(self) -> list:
        """Up to 4 rounds. Return the findings still open, or [] after a clean round."""
        open_findings = []
        for round_no in range(1, MAX_ROUNDS + 1):
            text = self.read_copy(pl.plan_path(self.id))
            plan = pl.parse(text)
            tickets = {t: self.read_copy(f".tollgate/tickets/{t}/ticket.md") for t in plan.tickets}
            findings = []
            for lens in PLAN_LENSES:
                inputs = {"plan": text} if lens == "fresh_reader" else {
                    "plan": text, "tickets": tickets, "request": self.request}
                try:
                    data = self.role("reviewer", inputs, lens=lens)
                except roles.RoleError:
                    try:  # one retry, then the round does not count as clean
                        data = self.role("reviewer", inputs, lens=lens)
                    except roles.RoleError as err:
                        findings.append({"lens": lens, "level": "major",
                                         "text": f"the reviewer did not answer: {err}"})
                        continue
                self.log.add("plan_reviewed", lens=lens, round=round_no, cost_usd=data.cost_usd)
                findings += [dict(f, lens=lens) for f in data.data.get("findings", [])
                             if f.get("level") in OPEN_LEVELS]
            if not findings:
                self.log.add("plan_review_clean", round=round_no)
                return []
            answer = self.role("builder", {"mode": "answer", "findings": findings})
            answers = answer.data.get("answers", [])
            escalated = [findings[a["finding"]] for a in answers if a.get("action") == "escalate"
                         and isinstance(a.get("finding"), int) and a["finding"] < len(findings)]
            self.log.add("plan_answered", round=round_no, cost_usd=answer.cost_usd,
                         answers=answers, escalated=len(escalated))
            open_findings = escalated
            if escalated:
                return escalated
            problems = self.check_plan()
            if problems:
                self.write_plan(problems)
        return open_findings or [{"level": "major", "text": f"{MAX_ROUNDS} rounds with findings"}]

    def approve(self, open_findings: list) -> dict:
        reason = ("The plan review is clean." if not open_findings
                  else f"{len(open_findings)} findings are open after the review.")
        plan = self.read_copy(pl.plan_path(self.id))
        for entry in self.settings["ai"]["advisor"]:
            if entry == "person":
                return advisor.ask_person(self.server, self.log, self.log_path, f"plan {self.id}",
                                          f"{reason}\n\nThe plan:\n\n{plan}",
                                          ["approve", "send_back"], self.settings["approvers"])
            if self.ai_decisions >= 2:
                continue
            answer = self.role("advisor", {"plan": plan, "findings": open_findings,
                                           "reason": reason}, command=entry)
            self.ai_decisions += 1
            decision = answer.data.get("decision")
            self.log.add("advisor_decided", by="ai", decision=decision, cost_usd=answer.cost_usd,
                         hint=answer.data.get("hint", ""))
            if decision in ("approve", "send_back"):
                return {"decision": decision, "hint": answer.data.get("hint", "")}
        raise Parked("no advisor decided on the plan")

    def lock_plan(self):
        git(self.copy, "add", "-A", ".tollgate/plans", ".tollgate/tickets")
        git(self.copy, "commit", "-q", "--allow-empty", "-m", f"plan {self.id}")
        push(self.copy, "-q", "-f", "origin", f"HEAD:refs/heads/tg-plan/{self.id}")
        tag = self.server.lock_plan(self.id)
        self.log.add("plan_locked", tag=tag, commit=git(self.copy, "rev-parse", "HEAD"))

    def build_tickets(self) -> dict:
        plan = pl.parse(self.read_copy(pl.plan_path(self.id)))
        done = {e["ticket"]: e["code"] for e in read(self.log_path) if e["event"] == "ticket_done"}
        for tid in plan.tickets:
            if done.get(tid) == 0:
                continue
            target = Path(self.project, f".tollgate/tickets/{tid}/ticket.md")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.read_copy(f".tollgate/tickets/{tid}/ticket.md"))
            try:
                code = Driver(self.project, tid, self.server, self.base).run()
            except Busy:
                code = 4
            except (roles.RoleError, tk.TicketError, subprocess.CalledProcessError) as err:
                self.log.add("ticket_error", ticket=tid, error=str(err)[-500:])
                code = 1
            self.log.add("ticket_done", ticket=tid, code=code)
            done[tid] = code
        return done

    def run(self) -> int:
        lock = TicketLock(os.path.join(self.project, ".tollgate", "run", f"task-{self.id}.lock"))
        lock.acquire()
        try:
            events = read(self.log_path)
            kinds = {e["event"] for e in events}
            self.ai_decisions = sum(1 for e in events
                                    if e["event"] == "advisor_decided" and e.get("by") == "ai")
            with Log(self.log_path, task=self.id) as self.log:
                self.copy = roles.make_copy(self.project, f"task-{self.id}")
                git(self.copy, "fetch", "-q", "origin", "--tags", "--force")
                self.settings = st.load_from_ref(self.copy, self.base)
                self.log.add("started")
                if "plan_locked" not in kinds:
                    if "plan_review_done" not in kinds:
                        if "plan_written" not in kinds:
                            git(self.copy, "checkout", "-q", "-B", f"tg-plan/{self.id}", self.base)
                            self.write_plan()
                        open_findings = self.review_plan()
                        self.log.add("plan_review_done", open=open_findings)
                    else:
                        open_findings = [e for e in events
                                         if e["event"] == "plan_review_done"][-1]["open"]
                    try:
                        decision = self.approve(open_findings)
                    except advisor.Waiting as waiting:
                        raise Parked(str(waiting)) from None
                    if decision["decision"] != "approve":
                        self.log.add("plan_sent_back", hint=decision.get("hint", ""))
                        self.write_plan(hint=decision.get("hint", ""))
                        self.log.add("plan_review_done", open=self.review_plan())
                        raise Parked("the plan was sent back and needs a new approval")
                    self.lock_plan()
                done = self.build_tickets()
                path = report.write(self.project, self.id)
                self.log.add("reported", path=path, tickets=done)
                return 0 if all(c == 0 for c in done.values()) else 3
        except Parked as parked:
            Log(self.log_path, task=self.id).add("task_waiting", reason=str(parked))
            report.write(self.project, self.id)
            return 3
        finally:
            lock.release()


def main(argv=None, server=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate task", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--request", help="the request, in your own words")
    parser.add_argument("--request-file")
    parser.add_argument("--repository")
    args = parser.parse_args(argv)
    request = args.request or (Path(args.request_file).read_text() if args.request_file else "")
    if not request.strip():
        print("tollgate task: give --request or --request-file", file=sys.stderr)
        return 1
    if server is None:
        from driver.server import GitHub
        server = GitHub.for_project(args.project, args.repository)
    try:
        return Task(args.project, args.task, request, server).run()
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (roles.RoleError, pl.PlanError, st.SettingsError, OSError,
            subprocess.CalledProcessError) as err:
        print(f"tollgate task: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
