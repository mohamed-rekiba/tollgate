"""Build a roadmap: freeze its checklist, run each task in order, then check the whole.

The task skill starts this for a request too large for one plan, after it writes
the roadmap file and its checklist ticket in the project's working folder.
A task that does not finish stops the roadmap, because later tasks build on it.
After the base tasks, the base suite must pass before the skeleton starts.
Exit codes as for driver.task.

This command runs a roadmap in background mode: its tasks and tickets start each
role as its own process. For `runner: "session"`, the task skill runs the same
roadmap with `driver.step next --roadmap <id>` instead: run() then takes
runner="session", and ends with 5 when a role waits for your session. A pause
logs nothing here, so the next run goes on with the task or the checklist where
it stopped.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from driver.driver import BASE, Busy, Driver, run_lock
from driver.log import Log, read
from driver.task import Task
from gate import roadmap as rm
from gate import settings as st
from gate import state
from gate.store import Store
from setup import base_suite

BACKGROUND = "background"
PAUSED = 5    # a role waits for your session; see driver/session.py


def check_base(project: str, log, ref: str = BASE) -> int:
    """Run the base suite with the settings on main. Log it; 0 when all five pass."""
    try:
        settings = st.load_from_ref(project, ref)
    except (st.SettingsError, OSError, ValueError, subprocess.CalledProcessError) as err:
        log.add("roadmap_waiting", reason=f"cannot read the settings on {ref} for the base "
                                          f"suite: {err}")
        return 1
    try:
        results = base_suite.run(settings, project)
    except OSError as err:
        log.add("roadmap_waiting", reason=f"the base suite could not run: {err}")
        return 1
    failed = [r for r in results if not r["passed"]]
    if failed:
        log.add("roadmap_waiting", reason="the base is not ready: " + "; ".join(
            f"{r['name']} ({r['why']})" for r in failed), base=results)
        return 1
    log.add("base_passed", base=results)
    return 0


def run(project: str, roadmap_id: str, store=None, runner: str = BACKGROUND) -> int:
    """Run the roadmap from where its log says it stopped. runner is "background", or
    "session" for driver.step."""
    project = os.path.abspath(project)
    store = store or Store(project)
    roadmap = rm.parse(Path(project, rm.roadmap_path(roadmap_id)).read_text())
    log_path = str(state.path(project, "logs", f"roadmap-{roadmap_id}.jsonl"))
    lock = run_lock(project, f"roadmap-{roadmap_id}")
    lock.acquire()
    try:
        done = {e["task"]: e["code"] for e in read(log_path) if e["event"] == "task_done"}
        frozen = any(e["event"] == "checklist_frozen" for e in read(log_path))
        with Log(log_path, roadmap=roadmap_id) as log:
            if not frozen:
                code = Driver(project, roadmap.checklist, store, runner=runner).run(until="frozen")
                if code == PAUSED:
                    return code
                if code != 0:
                    log.add("roadmap_waiting", reason="the checklist could not be frozen")
                    return code
                log.add("checklist_frozen", ticket=roadmap.checklist)
            base_checked = any(e["event"] == "base_passed" for e in read(log_path))
            for stage, task_id, request in roadmap.tasks:
                if stage != "Base" and not base_checked:
                    # The base is done: it must prove the five things before the rest builds on it.
                    code = check_base(project, log)
                    if code != 0:
                        return code
                    base_checked = True
                if done.get(task_id) == 0:
                    continue
                code = Task(project, task_id, request, store, runner=runner).run()
                if code == PAUSED:
                    return code
                log.add("task_done", stage=stage, task=task_id, code=code)
                if code != 0:
                    log.add("roadmap_waiting", reason=f"task {task_id} did not finish")
                    return code
            if not base_checked:
                code = check_base(project, log)
                if code != 0:
                    return code
            code = Driver(project, roadmap.checklist, store, runner=runner).run()
            if code == PAUSED:
                return code
            log.add("roadmap_done" if code == 0 else "roadmap_waiting", checklist_code=code)
            return code
    finally:
        lock.release()


def main(argv=None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate roadmap", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--roadmap", required=True)
    args = parser.parse_args(argv)
    try:
        return run(args.project, args.roadmap, store)
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (rm.RoadmapError, st.SettingsError, OSError) as err:
        print(f"tollgate roadmap: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
