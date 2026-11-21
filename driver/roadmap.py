"""Build a roadmap: freeze its checklist, run each task in order, then check the whole.

    PYTHONPATH=<tollgate> python3 -m driver.roadmap --project . --roadmap orders

The roadmap file and its checklist ticket are in the project's working folder.
A task that does not finish stops the roadmap, because later tasks build on it.
Exit codes as for driver.task.
"""

import argparse
import os
import sys
from pathlib import Path

from action import roadmap as rm
from driver.driver import Busy, Driver, TicketLock
from driver.log import Log, read
from driver.task import Task


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
            for stage, task_id, request in roadmap.tasks:
                if done.get(task_id) == 0:
                    continue
                code = Task(project, task_id, request, server).run()
                log.add("task_done", stage=stage, task=task_id, code=code)
                if code != 0:
                    log.add("roadmap_waiting", reason=f"task {task_id} did not finish")
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
