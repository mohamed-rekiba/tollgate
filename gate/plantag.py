"""Build the lock of an approved plan: the fingerprints of the plan and its tickets.

`Store.lock_plan` signs the record into plans/<task>.json. This module reads
the plan and its tickets as files at one commit and runs none of the project's code.
"""

from gate import plan as pl
from gate.gitio import fingerprint, show_bytes


def record(repo, task_id: str, commit: str) -> dict:
    """Return {task, commit, files} for the plan at a commit. Raise PlanError when it is not valid."""
    if not pl.ID.match(task_id or ""):
        raise pl.PlanError(f"not a valid task id: {task_id!r}")
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
    return {"task": task_id, "commit": commit, "files": files}
