"""Draw the project's diagrams as SVG, one light and one dark file for each.

    python3 docs/diagrams/build.py          # draw every diagram
    python3 docs/diagrams/build.py --check  # end with 1 if a drawn file is out of date

Two kinds of diagram:
- Written: a spec in docs/diagrams/src/<name>.json. The spec format is in
  driver/diagram.py.
- Read from the code: the spec is made here, from a file of the project, each
  time. When that file changes and the picture does not, --check fails, so
  the picture cannot drift from the code. "workflow" is the jobs of
  .github/workflows/tollgate.yml and the order they run in.
- Art: a picture drawn in its own code, such as the README banner in hero.py.
"""

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import hero

from driver.diagram import THEMES, draw

__all__ = ["THEMES", "build", "workflow_spec"]

# Who acts in each job of the workflow. A new job with no entry is neutral.
JOB_KINDS = {"freeze-test": "check", "freeze-lock": "server", "plan-lock": "server",
             "task": "ai", "plain": "ai", "e2": "ai", "find": "server", "test": "check",
             "review": "check", "gate": "check"}


def workflow_jobs(text: str) -> list:
    """The jobs of a workflow, in file order: name, needs, trigger, and the comment above it."""
    jobs, comment = [], []
    body = text[text.index("\njobs:\n"):]
    for line in body.splitlines():
        if re.match(r"^  # ", line):
            comment.append(line[4:].strip())
            continue
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            jobs.append({"name": m.group(1), "needs": [], "kind": None,
                         "about": " ".join(comment)})
            comment = []
            continue
        if not line.startswith("   "):
            comment = []
        if not jobs:
            continue
        m = re.match(r"^    needs:\s*\[?([^\]]+)\]?\s*$", line)
        if m:
            jobs[-1]["needs"] = [n.strip() for n in m.group(1).split(",")]
        m = re.search(r"inputs\.kind == '([a-z0-9-]+)'", line)
        if m and jobs[-1]["kind"] is None and line.startswith("    if:"):
            jobs[-1]["kind"] = m.group(1)
    return jobs


def implied(jobs) -> set:
    """Needs that a longer path already shows, such as find -> gate when find -> test -> gate."""
    needs = {j["name"]: set(j["needs"]) for j in jobs}

    def reach(start, seen):
        for n in needs[start]:
            if n not in seen:
                seen.add(n)
                reach(n, seen)
        return seen

    return {(a, j) for j in needs for a in needs[j]
            if any(a in reach(b, set()) for b in needs[j] - {a})}


def about(text: str) -> list:
    """The first sentence of a job's comment, in at most three short lines."""
    first = re.split(r"(?<=\.)\s", text)[0].rstrip(".")
    lines = textwrap.wrap(first, 38) or ["(no comment above the job)"]
    if len(lines) > 3:
        lines = lines[:3]
        lines[2] = lines[2].rstrip(",;:") + "…"
    return lines


def workflow_spec() -> dict:
    jobs = workflow_jobs((ROOT / ".github" / "workflows" / "tollgate.yml").read_text())
    needed = {n for j in jobs for n in j["needs"]}
    depth, row, taken, nodes = {}, {}, set(), []
    for job in jobs:
        depth[job["name"]] = 1 + max((depth[n] for n in job["needs"]), default=-1)
    next_row, alone_col = 0, 0
    for job in jobs:
        name = job["name"]
        if not job["needs"] and name not in needed:
            # A job on its own: two to a row.
            col, r = alone_col, next_row
            alone_col = 1 - alone_col
            if alone_col == 0:
                next_row += 1
        else:
            if alone_col == 1:
                alone_col, next_row = 0, next_row + 1
            col = depth[name]
            r = row[job["needs"][0]] if job["needs"] else next_row
            while (col, r) in taken:
                r += 1
            next_row = max(next_row, r + 1)
        taken.add((col, r))
        row[name] = r
        tag = f"DISPATCH · {job['kind'].upper()}" if job["kind"] else (
            "AFTER " + ", ".join(job["needs"]).upper() if job["needs"] else "PULL REQUEST")
        node = {"id": name, "text": "\n".join([name, *about(job["about"])]), "col": col, "row": r,
                "tag": tag}
        if JOB_KINDS.get(name):
            node["kind"] = JOB_KINDS[name]
        nodes.append(node)
    skip = implied(jobs)
    edges = []
    for job in jobs:
        for n in job["needs"]:
            if (n, job["name"]) in skip:
                continue
            edge = {"from": n, "to": job["name"]}
            if row[job["name"]] < row[n]:
                edge["route"] = "hv"  # across, then up, so it does not share a line
            edges.append(edge)
    names = ", ".join(j["name"] for j in jobs)
    return {
        "title": "The jobs of the Tollgate workflow",
        "desc": (f"The jobs of .github/workflows/tollgate.yml, drawn from the file itself: "
                 f"{names}. An arrow means a job waits for the one before it. Each box says "
                 f"what starts the job and what it does."),
        "nodes": nodes, "edges": edges,
    }


GENERATED = {"workflow": workflow_spec}
# Drawn by hand in code, not from a spec.
ART = {"hero": hero.draw}


def specs() -> dict:
    out = {src.stem: json.loads(src.read_text()) for src in sorted((HERE / "src").glob("*.json"))}
    out.update({name: make() for name, make in GENERATED.items()})
    return out


def build(check=False) -> list:
    """Draw every diagram. Return the files that changed, or with check, that would."""
    stale = []
    drawings = {name: (lambda theme, spec=spec: draw(spec, theme)) for name, spec in specs().items()}
    drawings.update(ART)
    for name, make in drawings.items():
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            target = HERE / f"{name}{suffix}.svg"
            text = make(theme)
            if not target.exists() or target.read_text() != text:
                stale.append(target.name)
                if not check:
                    target.write_text(text)
    return stale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="change nothing; end with 1 if stale")
    args = parser.parse_args(argv)
    stale = build(args.check)
    for name in stale:
        print(("out of date: " if args.check else "drew ") + name)
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
