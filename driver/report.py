"""The report of a task, and the status of every ticket, read from the logs.

    PYTHONPATH=<tollgate> python3 -m driver.report --project .            # status
    PYTHONPATH=<tollgate> python3 -m driver.report --project . --task retries
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from driver.driver import cost_of
from driver.log import read

STATES = {
    "merged": "merged", "waiting_for_merge": "pull request open", "pr_opened": "pull request open",
    "parked": "parked", "waiting_for_advisor": "waits for a person", "still_waiting":
    "waits for a person", "stopped": "stopped", "attempt_passed": "building",
    "attempt_failed": "building", "attempt_started": "building", "frozen": "frozen",
    "tests_reviewed": "tests written", "tests_written": "tests written", "started": "started",
}


def logs_dir(project: str) -> Path:
    return Path(project, ".tollgate", "logs")


def ticket_row(events: list) -> dict:
    state = "not started"
    for e in reversed(events):
        if e["event"] in STATES:
            state = STATES[e["event"]]
            break
    attempts = [e for e in events if e["event"] in ("attempt_failed", "attempt_passed")]
    best = max((e.get("score", -1) for e in attempts), default=-1)
    pr = next((e["pr"] for e in reversed(events) if e["event"] == "pr_opened"), None)
    reason = next((e.get("reason", "") for e in reversed(events)
                   if e["event"] in ("parked", "waiting_for_advisor", "stopped")), "")
    tier = next((e["tier"] for e in reversed(attempts) if "tier" in e), None)
    return {"ticket": events[0].get("ticket", "?") if events else "?", "state": state,
            "tier": tier, "attempts": len(attempts), "score": best if best >= 0 else None,
            "cost_usd": cost_of(events), "pr": pr, "reason": reason,
            "task": events[0].get("task", "") if events else ""}


def rows(project: str, task: str | None = None) -> list:
    out = []
    for path in sorted(logs_dir(project).glob("*.jsonl")):
        if path.name.startswith("task-"):
            continue
        events = read(str(path))
        if events and (task is None or events[0].get("task") == task):
            out.append(ticket_row(events))
    return out


def _minutes(events: list) -> int:
    stamps = [datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
              for e in events if "at" in e]
    return round((max(stamps) - min(stamps)).total_seconds() / 60) if stamps else 0


def render(project: str, task: str) -> str:
    task_events = read(str(logs_dir(project) / f"task-{task}.jsonl"))
    tickets = rows(project, task)
    all_events = task_events + [e for p in logs_dir(project).glob("*.jsonl")
                                if not p.name.startswith("task-")
                                for e in read(str(p)) if e.get("task") == task]
    plan_cost = cost_of(task_events)
    total = round(plan_cost + sum(r["cost_usd"] for r in tickets), 4)
    waiting = [e for e in task_events if e["event"] == "task_waiting"]
    lines = [f"# Report: task {task}", "",
             f"- Cost: {total} USD ({plan_cost} USD for the plan).",
             f"- Time: {_minutes(all_events)} minutes from the first event to the last.",
             f"- Plan: {'locked' if any(e['event'] == 'plan_locked' for e in task_events) else 'not locked'}.",
             ""]
    if waiting:
        lines += [f"The task waits: {waiting[-1]['reason']}", ""]
    lines += ["| Ticket | State | Tier | Attempts | Score | Cost USD | Pull request | Why |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in tickets:
        lines.append(f"| {r['ticket']} | {r['state']} | {r['tier'] or ''} | {r['attempts']} | "
                     f"{'' if r['score'] is None else r['score']} | {r['cost_usd']} | "
                     f"{'#' + str(r['pr']) if r['pr'] else ''} | {r['reason']} |")
    advisor_events = [e for e in all_events if e["event"] in ("waiting_for_advisor",
                                                              "advisor_decided")]
    asked = sum(1 for e in advisor_events if e["event"] == "waiting_for_advisor")
    decided = sum(1 for e in advisor_events if e["event"] == "advisor_decided")
    lines += ["", f"The advisor was asked {asked} times and decided {decided} times."]
    return "\n".join(lines) + "\n"


def write(project: str, task: str) -> str:
    path = Path(project, ".tollgate", "reports", f"{task}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(project, task))
    return str(path)


def status(project: str) -> str:
    found = rows(project)
    if not found:
        return "Tollgate: no tickets have run in this project yet."
    lines = ["| Task | Ticket | State | Tier | Attempts | Score | Cost USD | Pull request |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in found:
        lines.append(f"| {r['task']} | {r['ticket']} | {r['state']} | {r['tier'] or ''} | "
                     f"{r['attempts']} | {'' if r['score'] is None else r['score']} | "
                     f"{r['cost_usd']} | {'#' + str(r['pr']) if r['pr'] else ''} |")
    waiting = [r for r in found if r["state"] in ("waits for a person", "parked")]
    if waiting:
        lines += ["", "Waiting for a decision:"] + [f"- {r['ticket']}: {r['reason']}" for r in waiting]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate report", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--task")
    args = parser.parse_args(argv)
    if args.task:
        print(write(args.project, args.task))
    else:
        print(status(args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
