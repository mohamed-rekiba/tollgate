"""The numbers of a task, and up to 3 candidates for lessons.

    PYTHONPATH=<tollgate> python3 -m driver.retro --project . --task retries

It writes .tollgate/lessons/<task id>.md. A lesson becomes a test, a check, a
change to a lens, or a stricter rule. The retro skill turns each candidate into
a ticket. Tollgate can make a rule stricter. Only a person makes a rule looser.
"""

import argparse
import sys
from pathlib import Path

from driver.log import read
from driver.report import logs_dir, ticket_row

MAX_LESSONS = 3


def numbers(project: str, task: str) -> dict:
    tickets = []
    for path in sorted(logs_dir(project).glob("*.jsonl")):
        if path.name.startswith(("task-", "roadmap-")):
            continue
        events = read(str(path))
        if events and events[0].get("task") == task:
            tickets.append((ticket_row(events), events))
    n = len(tickets)

    def share(pred):
        return round(100 * sum(1 for row, ev in tickets if pred(row, ev)) / n) if n else 0

    return {
        "tickets": n,
        "reached_advisor_pct": share(lambda r, ev: any(e["event"] in (
            "waiting_for_advisor", "advisor_decided") for e in ev)),
        "first_attempt_pass_pct": share(lambda r, ev: any(
            e["event"] == "attempt_passed" and e.get("attempt") == 1 for e in ev)),
        "parked": sum(1 for r, _ in tickets if r["state"] == "parked"),
        "mean_attempts": round(sum(r["attempts"] for r, _ in tickets) / n, 2) if n else 0,
        "cost_per_ticket_usd": round(sum(r["cost_usd"] for r, _ in tickets) / n, 4) if n else 0,
        "tests_rejected": sum(1 for _, ev in tickets for e in ev if e["event"] == "tests_rejected"),
    }, tickets


def candidates(tickets: list) -> list:
    """The tickets with the most trouble first: stops, then rejected tests, then attempts."""
    scored = []
    for row, events in tickets:
        stops = [e["reason"] for e in events if e["event"] == "stopped"]
        rejected = sum(1 for e in events if e["event"] == "tests_rejected")
        if not stops and not rejected and row["attempts"] <= 1:
            continue
        kind = ("check" if any("same checks" in s for s in stops) else
                "lens" if rejected else "test" if row["attempts"] > 1 else "rule")
        scored.append(((len(stops), rejected, row["attempts"]), {
            "ticket": row["ticket"], "kind": kind,
            "evidence": stops[-1] if stops else f"{rejected} rejected tests, "
                                                f"{row['attempts']} attempts"}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:MAX_LESSONS]]


def write(project: str, task: str) -> str:
    nums, tickets = numbers(project, task)
    cands = candidates(tickets)
    lines = [f"# Retro: task {task}", "", "| Number | Value |", "| --- | --- |"]
    lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in nums.items()]
    lines += ["", f"## Candidates for lessons (at most {MAX_LESSONS})", ""]
    lines += [f"- {c['ticket']}: a {c['kind']}. Evidence: {c['evidence']}" for c in cands] or [
        "- None. No ticket stopped, had a test rejected, or needed a second attempt."]
    path = Path(project, ".tollgate", "lessons", f"{task}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate retro", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    print(write(args.project, args.task))
    return 0


if __name__ == "__main__":
    sys.exit(main())
