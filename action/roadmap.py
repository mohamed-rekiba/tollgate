"""Read and check a roadmap: .tollgate/roadmaps/<id>.md.

A roadmap is an ordered list of tasks for a request too large for one plan:

    ---
    id: orders
    checklist: orders-done
    ---
    ## Request             the whole request, in the asker's words
    ## Base                tasks that make the project build, test, and run
    - orders-base: Make the project build, test, and run with the base suite.
    ## Skeleton            the shared rules, then one thin path that works
    - orders-rules: One error shape, one API format, the login check, the log fields.
    ## Features            only the features that are clear now
    - orders-create: Create an order.
    ## Not yet specified   everything else, in a few words

`checklist` names a ticket, .tollgate/tickets/<id>/ticket.md, whose checklist is
the checklist of the whole request. Its tests are frozen before the first task
and must pass after the last.
"""

import re
from dataclasses import dataclass

from action.plan import ID

ROADMAPS = ".tollgate/roadmaps"
STAGES = ("Base", "Skeleton", "Features")
SECTIONS = ("Request", *STAGES, "Not yet specified")
TASK_LINE = re.compile(r"^- ([A-Za-z0-9][A-Za-z0-9._-]{0,63}):\s+(\S.*)$")


class RoadmapError(ValueError):
    pass


@dataclass
class Roadmap:
    id: str
    checklist: str
    request: str
    tasks: list  # [(stage, task id, request)] in build order


def roadmap_path(roadmap_id: str) -> str:
    return f"{ROADMAPS}/{roadmap_id}.md"


def parse(text: str) -> Roadmap:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        raise RoadmapError("a roadmap starts with a header between two --- lines")
    end = lines.index("---", 1)
    header = {}
    for line in lines[1:end]:
        if line.strip():
            key, _, value = line.partition(":")
            if key.strip() not in ("id", "checklist"):
                raise RoadmapError(f"unknown header line: {line!r}")
            header[key.strip()] = value.strip()
    for key in ("id", "checklist"):
        if not ID.match(header.get(key, "")):
            raise RoadmapError(f"the roadmap header needs a valid {key}")
    sections, current = {}, None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    missing = [s for s in SECTIONS if s not in sections]
    if missing:
        raise RoadmapError(f"the roadmap has no section: {', '.join(missing)}")
    if not "".join(sections["Request"]).strip():
        raise RoadmapError("the Request section is empty")
    tasks, seen = [], set()
    for stage in STAGES:
        for line in sections[stage]:
            if not line.strip():
                continue
            m = TASK_LINE.match(line.strip())
            if not m:
                raise RoadmapError(f"not a task line in {stage}: {line!r}")
            if m.group(1) in seen:
                raise RoadmapError(f"task {m.group(1)} appears twice")
            seen.add(m.group(1))
            tasks.append((stage, m.group(1), m.group(2)))
    if not tasks:
        raise RoadmapError("the roadmap lists no tasks")
    if header["checklist"] in seen:
        raise RoadmapError("the checklist ticket cannot also be a task")
    return Roadmap(header["id"], header["checklist"], "\n".join(sections["Request"]).strip(),
                   tasks)
