"""Session mode, one step at a time: your own Claude Code session runs each role.

    PYTHONPATH=<tollgate> python3 -P -m driver.step next --project . --task <task id>
    PYTHONPATH=<tollgate> python3 -P -m driver.step answer --project . --key <key> --nonce <nonce> < answer.md

`next` runs the task's driver in session mode, from its log and the saved
answers, up to the next role. It prints one JSON object:

- a step: {"agent": "tollgate:<role>", "prompt": ..., "cwd": ..., "key": ...,
  "nonce": ...}. Start that subagent in that folder with that prompt, then pipe
  its whole final answer to `answer` with that key and that nonce. The nonce is
  new for each `next`, and the step file keeps only its hash, so only the session
  that ran `next` can answer.
- the end: {"done": true, "result": <done and still to do>, "merged": [tickets],
  "report": <path>}.
- a question for a person: {"question": {"n", "title", "body", "options"}}.
  Record the person's answer with setup.inbox, then run `next` again.
- a ticket parked with no question: {"parked": <the reason>}.
- an error: {"error": <the reason>}, and the command ends with 1.

`answer` refuses a key or a nonce that is not the waiting step's, and never
says what they are; and an answer with no final json block. A role cannot run
this command: the hook refuses any Tollgate command from a role. It saves the answer, then runs `next` and prints what
`next` prints. The request of the task is .tollgate/requests/<task id>.md.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from driver import advisor, history, report, roles, session
from driver.driver import Busy, run_lock
from driver.log import read
from driver.task import Task
from gate import plan as pl
from gate import settings as st
from gate import state
from gate.store import Store, StoreError


def _request(project: str, task: str) -> str:
    path = Path(project, ".tollgate", "requests", f"{task}.md")
    if not path.exists():
        raise session.NotReady(f"the request is missing: write it to {path}")
    return path.read_text()


def _question(project: str, task: str, store) -> dict | None:
    """The open question of the task or of one of its tickets, or None."""
    logs = state.path(project, "logs")
    for path in [logs / f"task-{task}.jsonl", *history.logs(logs)]:
        events = read(str(path))
        if path.name.startswith("task-") and path.name != f"task-{task}.jsonl":
            continue
        if not path.name.startswith("task-") and not any(e.get("task") == task for e in events):
            continue
        found = history.open_question(events)
        if found:
            q = advisor.question(store, found["question"]) or {}
            return {"n": found["question"], "title": q.get("title", ""),
                    "body": q.get("body", found["reason"]), "options": q.get("options", [])}
    return None


def _merged(project: str, task: str) -> list:
    out = []
    for path in history.logs(state.path(project, "logs")):
        if path.name.startswith(("task-", "roadmap-")):
            continue
        events = read(str(path))
        if any(e["event"] == "merged" and e.get("task") == task for e in events):
            out.append(events[0].get("ticket", path.stem))
    return out


def next_step(project: str, task: str, store=None) -> tuple:
    """Run the task to its next step. Return (what to print, exit code)."""
    project = str(Path(project).resolve())
    problem = session.cannot_pass(project)
    if problem:
        return {"error": problem}, 1
    store = store or Store(project)
    try:
        request = _request(project, task)
        code = Task(project, task, request, store, runner="session").run()
    except Busy as err:
        return {"error": str(err)}, 1
    except (roles.RoleError, pl.PlanError, st.SettingsError, StoreError, OSError,
            subprocess.CalledProcessError) as err:
        return {"error": str(err)}, 1
    if code == 5:
        # The nonce goes in under the task's run lock, so a second next cannot interleave.
        lock = run_lock(project, f"task-{task}")
        try:
            lock.acquire()
        except Busy as err:
            return {"error": str(err)}, 1
        try:
            step = session.read_step(project)
            if step is None:
                return {"error": "the driver paused, but no step file is there; run next "
                                 "again"}, 1
            nonce = session.new_nonce(project)
        finally:
            lock.release()
        return {"agent": step.get("agent", ""), "prompt": step["prompt"],
                "cwd": step.get("copy") or project, "key": step["key"], "nonce": nonce}, 0
    if code == 0:
        return {"done": True, "result": report.brief(project, task),
                "merged": _merged(project, task),
                "report": str(state.path(project, "reports", f"{task}.md"))}, 0
    question = _question(project, task, store)
    if question:
        return {"question": question}, 0
    if code == 3:
        waiting = report.still_waiting(read(str(state.path(project, "logs",
                                                           f"task-{task}.jsonl"))))
        parked = [f"{r['ticket']}: {r['reason']}" for r in report.rows(project, task)
                  if r["state"] == "parked"]
        return {"parked": waiting[-1]["reason"] if waiting else
                "; ".join(parked) or "the task waits"}, 0
    return {"error": f"the driver ended with {code}"}, 1


def answer(project: str, found_key: str, nonce: str, text: str, store=None) -> tuple:
    """Save the answer to the waiting step, then run next. Return (what to print, exit code)."""
    import hmac
    project = str(Path(project).resolve())
    step = session.read_step(project)
    if not step:
        return {"error": "no step waits for an answer; run next"}, 1
    wanted = str(step.get("nonce_sha256") or "")
    if not (hmac.compare_digest(found_key, step["key"]) and wanted
            and hmac.compare_digest(session.digest(nonce), wanted)):
        return {"error": "the key or the nonce is not the ones next printed for the step "
                         "that waits. Run next, and answer with what it prints."}, 1
    try:
        session.save_answer(project, step, text)
    except roles.RoleError as err:
        return {"error": f"the answer was not saved: {err}. The role must end its answer "
                         "with a ```json block."}, 1
    except (OSError, subprocess.CalledProcessError) as err:
        return {"error": f"the answer was not saved: {err}"}, 1
    return next_step(project, step["task"], store)


def main(argv=None, store=None, stdin=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate step", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    found = sub.add_parser("next", help="run the task to its next step")
    found.add_argument("--project", default=".")
    found.add_argument("--task", required=True)
    given = sub.add_parser("answer", help="save the answer to the waiting step (on stdin)")
    given.add_argument("--project", default=".")
    given.add_argument("--key", required=True)
    given.add_argument("--nonce", required=True)
    args = parser.parse_args(argv)
    if args.command == "next":
        out, code = next_step(args.project, args.task, store)
    else:
        out, code = answer(args.project, args.key, args.nonce, (stdin or sys.stdin).read(),
                           store)
    print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
