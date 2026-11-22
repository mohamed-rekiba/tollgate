"""The task loop: analysis, plan, plan review, approval, plan lock, each ticket in
order, then a review of the whole task.

    PYTHONPATH=<tollgate> python3 -m driver.task --project . --task retries --request-file r.txt

The task's own log is logs/task-<task id>.jsonl in the state folder, and its
copy is builders/task-<task id>/. Each ticket keeps its own log. A task that
starts again repeats no finished step. A ticket that waits for the advisor or is
parked does not stop the others: the report says why.

The setting `checkpoints` names where the advisor decides whether the task goes
on: "plan" (the approval of the plan), "ticket" (after each ready ticket), and
"task" (after the review of the whole task). A plan with an assumption, a plan
review with open findings, and a task review that blocks go to the advisor even
when their checkpoint is off.

A task starts only when it can pass: the settings on main name signers, and this
machine has its machine key. Otherwise it stops at once and says to run
/tollgate:init.

In a task the tickets build one on another: each starts from the ready change of
the ticket before it, and none merges until the review of the whole task passes.
Then the tickets merge in plan order, as far as auto merge and their tiers allow.
When the first review of the whole task finds a blocking or major problem, the
task runs one fix round: the builder changes the plan with the findings as its
hint, the plan is reviewed, approved, and locked again, and the new tickets are
built. A second failed review goes to the task checkpoint.

Exit codes: 0 every ticket is a ready change or merged, 3 something waits for the
advisor, 4 another driver holds the task, 5 a role waits for your session (see
driver/session.py), 1 an error.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from driver import advisor, report, roles, session
from driver.driver import BASE, Busy, Driver, Parked, fetch_branch, git, run_lock
from driver.log import Log, read
from gate import analysis as an
from gate import plan as pl
from gate import review as reviewlib
from gate import settings as st
from gate import state
from gate import tickets as tk
from gate.store import Store, StoreError

PLAN_LENSES = ("simplicity", "fresh_reader", "readiness")
MAX_ROUNDS = 4
OPEN_LEVELS = ("blocking", "major")
TASK_TIER = 2   # the review of the whole task reads like a tier 2 review: the review lens only
FIX_ROUNDS = 1  # the fix rounds a task may run after a failed review of the whole task


class Task:
    def __init__(self, project: str, task_id: str, request: str, store=None, driver_args=None,
                 runner: str | None = None):
        if not pl.ID.match(task_id):
            raise pl.PlanError(f"not a valid task id: {task_id!r}")
        self.project = os.path.abspath(project)
        self.id = task_id
        self.request = request
        self.store = store or Store(self.project)
        self.driver_args = driver_args or {}
        self.base = BASE
        self.logs = state.path(self.project, "logs")
        self.log_path = str(self.logs / f"task-{task_id}.jsonl")
        self.ai_decisions = 0
        self.runner = runner    # None: the setting `runner` decides
        self.caller = None

    def role(self, name, inputs, lens=None, command=None):
        s = self.settings
        command = command or (s["ai"]["reviewer"] if name in ("reviewer", "analyst")
                              else s["ai"]["builder"])
        # The builder writes the plan here, so it may write plans and tickets.
        policy = "planner" if name == "builder" else name
        return self.caller(session.Call(name, inputs, lens, command, policy, self.copy,
                                        self.project, f"task-{self.id}", "", self.id))

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
                if state.path(self.project, "locks", f"{t}.json").exists()
                and not Path(self.logs, f"{t}.jsonl").exists()]
        problems = [f"ticket id {t} is already used by an earlier lock; pick a new id"
                    for t in used]
        return problems + self.kept_tickets(plan) + pl.check_tickets(plan, self.read_copy)

    def kept_tickets(self, plan) -> list:
        """A new version of a locked plan keeps each ticket of the old one, unchanged."""
        path = state.path(self.project, "plans", f"{self.id}.json")
        if not path.exists():
            return []
        from gate.gitio import fingerprint
        problems = []
        for name, digest in json.loads(path.read_text())["files"].items():
            if not (name.startswith(".tollgate/tickets/") and name.endswith("/ticket.md")):
                continue
            tid = Path(name).parent.name
            text = self.read_copy(name)
            if tid not in plan.tickets or text is None or fingerprint(text.encode()) != digest:
                problems.append(f"ticket {tid} is locked by the approved plan; keep it, unchanged, "
                                "and add new tickets for the fix")
        return problems

    def analysis_text(self) -> str:
        found = [e for e in read(self.log_path) if e["event"] == "analysis_written"]
        return found[-1]["text"] if found else ""

    # Steps.

    def analyze(self):
        """The analyst reads the copy at main and answers with the analysis. The driver
        checks it, makes each citation that does not exist an assumption, and keeps the
        text in the log, so no later role can change it."""
        commit = git(self.copy, "rev-parse", "HEAD")
        problems = []
        for _ in range(3):
            answer = self.role("analyst", {"request": self.request, "task_id": self.id,
                                           "commit": commit, "problems": problems})
            try:
                found = an.parse(answer.data.get("analysis") or "")
                if (found.task, found.commit) != (self.id, commit):
                    raise an.AnalysisError(f"the header must say task: {self.id} and "
                                           f"commit: {commit}")
            except an.AnalysisError as err:
                problems = [str(err)]
                self.log.add("analysis_invalid", problems=problems, cost_usd=answer.cost_usd)
                continue
            missing = an.verify(found, self.copy)
            self.log.add("analysis_written", text=an.render(found), not_found=missing,
                         cost_usd=answer.cost_usd)
            return
        raise Parked("the analysis could not be read: " + "; ".join(problems))

    def write_plan(self, problems=None, hint=""):
        answer = self.role("builder", {"mode": "plan", "task_id": self.id, "request": self.request,
                                       "analysis": self.analysis_text(),
                                       "problems": problems or [], "hint": hint})
        self.log.add("plan_written", cost_usd=answer.cost_usd)
        for _ in range(2):
            problems = self.check_plan()
            if not problems:
                return
            self.log.add("plan_invalid", problems=problems)
            answer = self.role("builder", {"mode": "plan", "task_id": self.id,
                                           "request": self.request,
                                           "analysis": self.analysis_text(),
                                           "problems": problems})
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
                    "plan": text, "tickets": tickets, "request": self.request,
                    "analysis": self.analysis_text()}
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
        plan = self.read_copy(pl.plan_path(self.id))
        assumptions = pl.parse(plan).assumptions
        if "plan" not in self.settings["checkpoints"] and not open_findings and not assumptions:
            self.log.add("plan_approved", by="no checkpoint")
            return {"decision": "approve", "hint": ""}
        reason = ("The plan review is clean." if not open_findings
                  else f"{len(open_findings)} findings are open after the review.")
        if assumptions:
            reason += ("\n\nThe plan lists these assumptions. Send it back with your answers, "
                       "or approve it as it is:\n\n" + "\n".join(f"- {a}" for a in assumptions))
        for entry in self.settings["ai"]["advisor"]:
            if entry == "person":
                return advisor.ask_person(self.store, self.log, self.log_path, f"plan {self.id}",
                                          f"{reason}\n\nThe plan:\n\n{plan}",
                                          ["approve", "send_back"])
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

    def checkpoint(self, name: str, reason: str, inputs: dict, key: str = "") -> None:
        """Ask the advisor whether the task goes on. Return when it does; raise Parked
        when the advisor stops it or a person has not answered yet. A checkpoint does
        not count against the AI advisor's limit of decisions."""
        if self.stopped_at(name, key):
            raise Parked(f"the advisor stopped the task at the {name} checkpoint")
        subject = f"task {self.id}, {name} checkpoint" + (f" after {key}" if key else "")
        decision = None
        for entry in self.settings["ai"]["advisor"]:
            if entry == "person":
                try:
                    decision = advisor.ask_person(self.store, self.log, self.log_path, subject,
                                                  reason, ["continue", "stop"])
                except advisor.Waiting as waiting:
                    raise Parked(str(waiting)) from None
                break
            answer = self.role("advisor", {"checkpoint": name, "reason": reason, **inputs},
                               command=entry)
            decision = {"decision": answer.data.get("decision"),
                        "hint": answer.data.get("hint", "")}
            self.log.add("advisor_decided", by="ai", cost_usd=answer.cost_usd, checkpoint=name,
                         **decision)
            if decision["decision"] in ("continue", "stop"):
                break
            decision = None
        if decision is None:
            raise Parked(f"no advisor decided at the {name} checkpoint")
        if decision["decision"] == "stop":
            self.log.add("checkpoint_stopped", name=name, key=key, hint=decision["hint"])
            raise Parked(f"the advisor stopped the task at the {name} checkpoint")
        self.log.add("checkpoint_passed", name=name, key=key)

    def stopped_at(self, name: str, key: str = "") -> bool:
        """A stop holds: the task stays parked at that checkpoint when it starts again."""
        return any(e["event"] == "checkpoint_stopped" and e.get("name") == name
                   and e.get("key", "") == key for e in read(self.log_path))

    def passed_checkpoint(self, name: str, key: str = "") -> bool:
        return any(e["event"] == "checkpoint_passed" and e.get("name") == name
                   and e.get("key", "") == key for e in read(self.log_path))

    def lock_plan(self):
        # The analysis goes on the plan branch as the driver checked it.
        path = Path(self.copy, an.analysis_path(self.id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.analysis_text())
        git(self.copy, "add", "-A", ".tollgate/plans", ".tollgate/tickets", ".tollgate/analysis")
        git(self.copy, "commit", "-q", "--allow-empty", "-m", f"docs({self.id}): the plan")
        fetch_branch(self.project, self.copy, f"tg-plan/{self.id}")
        path = self.store.lock_plan(self.id)
        plan = pl.parse(self.read_copy(pl.plan_path(self.id)))
        self.log.add("plan_locked", path=path, commit=git(self.copy, "rev-parse", "HEAD"),
                     tickets=plan.tickets)

    def build_tickets(self) -> dict:
        plan = pl.parse(self.read_copy(pl.plan_path(self.id)))
        done = {e["ticket"]: e["code"] for e in read(self.log_path) if e["event"] == "ticket_done"}
        start = None    # each ticket starts from the ready change before it
        for tid in plan.tickets:
            if done.get(tid) == 0:
                self.ticket_checkpoint(tid)
                start = self.ready_commit(tid) or start
                continue
            text = self.read_copy(f".tollgate/tickets/{tid}/ticket.md")
            try:
                code = Driver(self.project, tid, self.store, ticket_text=text,
                              runner=self.runner, base=start, hold=True,
                              **self.driver_args).run()
            except Busy:
                code = 4
            except (roles.RoleError, tk.TicketError, StoreError,
                    subprocess.CalledProcessError) as err:
                self.log.add("ticket_error", ticket=tid, error=str(err)[-500:])
                code = 1
            if code == 5:
                # The ticket's role waits for your session; the task waits with it.
                raise session.Pause(session.read_step(self.project) or {"role": "role"})
            self.log.add("ticket_done", ticket=tid, code=code)
            done[tid] = code
            if code == 0:
                self.ticket_checkpoint(tid)
                start = self.ready_commit(tid) or start
        return done

    def ready_commit(self, tid: str) -> str:
        from driver import history
        return history.replay(read(str(Path(self.logs, f"{tid}.jsonl")))).ready

    def ticket_checkpoint(self, tid: str) -> None:
        if "ticket" in self.settings["checkpoints"] and not self.passed_checkpoint("ticket", tid):
            self.checkpoint("ticket", f"Ticket {tid} is a ready change. Go on to the next one?",
                            {"ticket": self.read_copy(f".tollgate/tickets/{tid}/ticket.md")}, tid)

    def fix_rounds(self) -> int:
        return sum(1 for e in read(self.log_path) if e["event"] == "fix_round")

    def review_task(self) -> bool:
        """The review lens reads every ticket's change together, against the plan. Return
        True when the task may merge. A blocking or major finding in the first round
        starts the fix round instead, and returns False. After it, a blocking finding,
        or the task checkpoint, goes to the advisor."""
        round_no = self.fix_rounds()
        found = [e for e in read(self.log_path)
                 if e["event"] == "task_reviewed" and e.get("round", 0) == round_no]
        if found:
            passed, text = found[-1]["passed"], found[-1]["text"]
            findings = found[-1].get("findings", [])
        else:
            plan = pl.parse(self.read_copy(pl.plan_path(self.id)))
            parts, reviewed = [], []
            for tid in plan.tickets:
                ready = [e for e in read(str(Path(self.logs, f"{tid}.jsonl")))
                         if e["event"] == "ready"]
                lock = state.path(self.project, "locks", f"{tid}.json")
                if ready and lock.exists():
                    # From the commit the ticket started on, so a merged ticket still counts.
                    start = json.loads(lock.read_text())["base_commit"]
                    parts.append(reviewlib.diff(self.project, start, ready[-1]["commit"]))
                    reviewed.append(tid)
            change = "\n".join(parts)[:reviewlib.DIFF_LIMIT]
            cost = []

            def run_role(lens, inputs):
                answer = self.role("reviewer", inputs, lens=lens)
                cost.append(answer.cost_usd)
                return answer.data

            passed, findings, text = reviewlib.review(
                TASK_TIER, self.read_copy(pl.plan_path(self.id)), change, run_role,
                lenses=("review",))
            self.log.add("task_reviewed", round=round_no, passed=passed, findings=findings,
                         text=text, tickets=reviewed, cost_usd=roles.add_cost(*cost))
        open_findings = [f for f in findings if f.get("level") in OPEN_LEVELS]
        if (not passed or open_findings) and round_no < FIX_ROUNDS:
            self.amend_plan(open_findings or findings)
            return False
        if (not passed or "task" in self.settings["checkpoints"]) \
                and not self.passed_checkpoint("task"):
            self.checkpoint("task", f"The review of the whole task:\n\n{text}", {"review": text})
        return True

    def amend_plan(self, findings: list) -> None:
        """The fix round: the builder changes the plan, with the findings of the review of
        the whole task as its hint; it keeps each locked ticket and adds tickets for the
        fix. Then the plan is reviewed, approved, and locked again. Each part is logged,
        so a task that starts again goes on where it stopped."""
        events = read(self.log_path)
        kinds = {e["event"] for e in events}
        hint = ("The review of the whole task found these problems. Keep every ticket of the "
                "plan as it is, and add the tickets that fix them, each with a locked test:\n"
                + "\n".join(f"- {f.get('level')}: {f.get('text', '')}"
                            + (f" ({f['file']}:{f.get('line', '')})" if f.get("file") else "")
                            for f in findings))
        if "fix_plan_reviewed" not in kinds:
            if "fix_plan_written" not in kinds:
                self.write_plan(hint=hint)
                self.log.add("fix_plan_written", findings=findings)
            open_findings = self.review_plan()
            self.log.add("fix_plan_reviewed", open=open_findings)
        else:
            open_findings = [e for e in events if e["event"] == "fix_plan_reviewed"][-1]["open"]
        try:
            decision = self.approve(open_findings)
        except advisor.Waiting as waiting:
            raise Parked(str(waiting)) from None
        if decision["decision"] != "approve":
            self.log.add("plan_sent_back", hint=decision.get("hint", ""))
            raise Parked("the plan of the fix round was sent back")
        self.lock_plan()
        self.log.add("fix_round", round=self.fix_rounds() + 1, findings=findings)

    def merge_ready(self) -> list:
        """Merge each ticket's ready change in plan order, once the review of the whole task
        passed. Stop at the first that may not merge: auto merge off, tier 3 or 4, or a
        merge the store refuses. Each later ticket holds the changes before it, so none
        may merge past it. Return the tickets merged."""
        plan = pl.parse(self.read_copy(pl.plan_path(self.id)))
        merged = []
        for tid in plan.tickets:
            path = str(Path(self.logs, f"{tid}.jsonl"))
            events = read(path)
            if any(e["event"] == "merged" for e in events):
                continue
            from driver import history
            t = history.replay(events)
            if not t.ready:
                return merged
            if not self.settings["auto_merge"] or t.tier is None or t.tier >= 3:
                return merged
            with Log(path, ticket=tid, task=self.id) as log:
                try:
                    merge = self.store.merge(t.ready)
                except StoreError as err:
                    log.add("waiting_for_merge", branch=f"tg/{tid}", commit=t.ready, tier=t.tier,
                            reason=f"the store did not merge: {err}")
                    return merged
                log.add("merged", commit=t.ready, merge=merge)
            roles.remove_copy(self.project, tid)
            merged.append(tid)
        return merged

    def run(self) -> int:
        problem = session.cannot_pass(self.project)
        if problem:
            raise session.NotReady(problem)
        lock = run_lock(self.project, f"task-{self.id}")
        lock.acquire()
        try:
            events = read(self.log_path)
            kinds = {e["event"] for e in events}
            self.ai_decisions = sum(1 for e in events if e["event"] == "advisor_decided"
                                    and e.get("by") == "ai" and "checkpoint" not in e)
            with Log(self.log_path, task=self.id) as self.log:
                self.copy = roles.make_copy(self.project, f"task-{self.id}")
                self.settings = st.load_from_ref(self.copy, self.base)
                self.caller = session.caller(self.settings, self.runner)
                if self.runner is None:
                    self.runner = self.settings["runner"]
                self.log.add("started")
                if "plan_locked" not in kinds:
                    if "plan_review_done" not in kinds:
                        if "plan_written" not in kinds:
                            if "analysis_written" not in kinds:
                                git(self.copy, "checkout", "-q", "-B", f"tg-plan/{self.id}",
                                    self.base)
                                self.analyze()
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
                while True:
                    done = self.build_tickets()
                    if not done or not all(c == 0 for c in done.values()):
                        break
                    if self.review_task():
                        self.merge_ready()
                        break
                path = report.write(self.project, self.id)
                self.log.add("reported", path=path, tickets=done)
                return 0 if all(c == 0 for c in done.values()) else 3
        except session.Pause:
            return 5
        except Parked as parked:
            Log(self.log_path, task=self.id).add("task_waiting", reason=str(parked))
            report.write(self.project, self.id)
            return 3
        finally:
            lock.release()


def main(argv=None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate task", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--request", help="the request, in your own words")
    parser.add_argument("--request-file")
    args = parser.parse_args(argv)
    request = args.request or (Path(args.request_file).read_text() if args.request_file else "")
    if not request.strip():
        print("tollgate task: give --request or --request-file", file=sys.stderr)
        return 1
    try:
        return Task(args.project, args.task, request, store).run()
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (roles.RoleError, pl.PlanError, st.SettingsError, StoreError, OSError,
            subprocess.CalledProcessError) as err:
        print(f"tollgate task: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
