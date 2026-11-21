"""Build a roadmap: freeze its checklist, run each task in order, then check the whole.

The task skill starts this for a request too large for one plan, after it writes
the roadmap file and its checklist ticket in the project's working folder.
A task that does not finish stops the roadmap, because later tasks build on it.
After the base tasks, the base suite must pass before the skeleton starts.
Exit codes as for driver.task.
"""

import argparse
import os
import sys
from pathlib import Path

from action import roadmap as rm
from action import settings as st
from driver.driver import Busy, Driver, TicketLock
from driver.log import Log, read
from driver.task import Task
from setup import base_suite


def check_base(project: str, log, ref: str = "origin/main") -> int:
    """Run the base suite with the settings on main. Log it; 0 when all five pass."""
    settings = st.load_from_ref(project, ref)
    results = base_suite.run(settings, project)
    failed = [r for r in results if not r["passed"]]
    if failed:
        log.add("roadmap_waiting", reason="the base is not ready: " + "; ".join(
            f"{r['name']} ({r['why']})" for r in failed), base=results)
        return 1
    log.add("base_passed", base=results)
    return 0


def run(project: str, roadmap_id: str, server) -> int:
    project = os.path.abspath(project)
    roadmap = rm.parse(Path(project, rm.roadmap_path(roadmap_id)).read_text())
    log_path = os.path.join(project, ".tollgate", "logs", f"roadmap-{roadmap_id}.jsonl")
    lock = TicketLock(os.path.join(project, ".tollgate", "run", f"roadmap-{roadmap_id}.lock"))
    lock.acquire()
    try:
        done = {e["task"]: e["code"] for e in read(log_path) if e["event"] == "task_done"}
        frozen = any(e["event"] == "checklist_frozen" for e in read(log_path))
        with Log(log_path, roadmap=roadmap_id) as log:
            if not frozen:
                code = Driver(project, roadmap.checklist, server).run(until="frozen")
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
                code = Task(project, task_id, request, server).run()
                log.add("task_done", stage=stage, task=task_id, code=code)
                if code != 0:
                    log.add("roadmap_waiting", reason=f"task {task_id} did not finish")
                    return code
            if not base_checked:
                code = check_base(project, log)
                if code != 0:
                    return code
            code = Driver(project, roadmap.checklist, server).run()
            log.add("roadmap_done" if code == 0 else "roadmap_waiting", checklist_code=code)
            return code
    finally:
        lock.release()


def main(argv=None, server=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate roadmap", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--roadmap", required=True)
    parser.add_argument("--repository")
    args = parser.parse_args(argv)
    if server is None:
        from driver.server import GitHub
        server = GitHub.for_project(args.project, args.repository)
    try:
        return run(args.project, args.roadmap, server)
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (rm.RoadmapError, OSError) as err:
        print(f"tollgate roadmap: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
