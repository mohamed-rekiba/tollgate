"""Build the message of a plan tag: tg/plan/<task id>/<number>.

The plan workflow runs this after an advisor approved the plan. It reads the
plan and its tickets as files at one commit and runs none of the project's code.
"""

import argparse
import json
import re
import sys

from gate import plan as pl
from gate.gitio import fingerprint, git, show_bytes

MAX_PLANS = 5
NUMBER = re.compile(r"[1-9][0-9]{0,3}", re.ASCII)


def next_number(repo, task_id: str) -> int:
    prefix = f"refs/tags/tg/plan/{task_id}/"
    refs = git(repo, "for-each-ref", "--format=%(refname)", prefix).split()
    numbers = [int(r[len(prefix):]) for r in refs if NUMBER.fullmatch(r[len(prefix):])]
    return max(numbers, default=0) + 1


def message(repo, task_id: str, commit: str, run_id: str) -> tuple:
    if not pl.ID.match(task_id):
        raise pl.PlanError(f"not a valid task id: {task_id!r}")
    number = next_number(repo, task_id)
    if number > MAX_PLANS:
        raise pl.PlanError(f"task {task_id} already has {MAX_PLANS} plan tags")
    data = show_bytes(repo, commit, pl.plan_path(task_id))
    if data is None:
        raise pl.PlanError(f"{pl.plan_path(task_id)} is not in commit {commit}")
    plan = pl.parse(data.decode())
    if plan.id != task_id:
        raise pl.PlanError(f"the plan names {plan.id}, not {task_id}")

    def read(path):
        raw = show_bytes(repo, commit, path)
        return raw.decode() if raw is not None else None

    problems = pl.check_tickets(plan, read)
    if problems:
        raise pl.PlanError("; ".join(problems))
    files = {pl.plan_path(task_id): fingerprint(data)}
    for tid in plan.tickets:
        path = f".tollgate/tickets/{tid}/ticket.md"
        files[path] = fingerprint(show_bytes(repo, commit, path))
    body = {"task": task_id, "commit": commit, "number": number, "run_id": int(run_id),
            "tickets": plan.tickets, "files": files}
    name = f"tg/plan/{task_id}/{number}"
    return name, f"Plan {number} of task {task_id}\n\n{json.dumps(body, indent=2, sort_keys=True)}\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate plantag", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--task", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--name-out", required=True)
    args = parser.parse_args(argv)
    try:
        name, text = message(args.repo, args.task, args.commit, args.run_id)
    except Exception as err:  # noqa: BLE001 - any failure refuses the plan tag
        print(f"the plan cannot be locked: {err}", file=sys.stderr)
        return 1
    with open(args.out, "w") as f:
        f.write(text)
    with open(args.name_out, "w") as f:
        f.write(name)
    print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
