"""Draw the project's diagrams as SVG, one light and one dark file for each.

    python3 docs/diagrams/build.py          # draw every diagram
    python3 docs/diagrams/build.py --check  # end with 1 if a drawn file is out of date

Two kinds of diagram:
- Written: a spec in docs/diagrams/src/<name>.json, a flow or a scene. The
  formats are in diagram/__init__.py and diagram/flow.py.
- Read from the code: the spec is made here, from a file of the project, each
  time. When that file changes and the picture does not, --check fails, so
  the picture cannot drift from the code. "workflow" is the jobs of
  .github/workflows/tollgate.yml and the order they run in.
- Art: a picture drawn in its own code, such as the README banner in hero.py.
"""

import argparse
import re
import sys
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import hero

from diagram import draw
from diagram.__main__ import build as build_folder
from diagram.flow import MONO, THEMES

__all__ = ["THEMES", "build", "workflow_spec"]

# What each job does, in plain words, for the picture. A new job with no entry
# shows the comment above it in the workflow file.
JOB_TEXT = {
    "freeze-test": ("Check the new tests", "runs them with read-only access"),
    "freeze-lock": ("Lock the tests", "so nobody can change them after"),
    "plan-lock": ("Lock the plan", "its tickets cannot change after"),
    "task": ("Build a whole task", "plan, tests, code, pull requests"),
    "plain": ("Build without Tollgate", "the same request, to compare"),
    "e2": ("Try the closed room", "an experiment: the AI with no network"),
    "find": ("Find the pull request", "and check its branch name"),
    "test": ("Run the tests", "with no secrets"),
    "review": ("Review the change", "an AI reads it and cannot edit"),
    "gate": ("Decide: pass or fail", "from the tests and the review"),
}
# Who acts in each job of the workflow. A new job with no entry is neutral.
JOB_ICONS = {"freeze-test": "test", "freeze-lock": "lock", "plan-lock": "lock", "task": "ai",
             "plain": "terminal", "e2": "terminal", "find": "pull-request", "test": "test",
             "review": "check", "gate": "gate"}
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


def _started_by_dispatch(job, jobs) -> bool:
    """A job that waits for a dispatched job, such as freeze-lock after freeze-test."""
    kinds = {j["name"]: j["kind"] for j in jobs}
    return any(kinds.get(n) for n in job["needs"])


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
        title, line = JOB_TEXT.get(name, (name, " ".join(about(job["about"]))))
        node = {"id": name, "text": "\n".join([title, line, f"job: {name}"]), "col": col, "row": r}
        if JOB_KINDS.get(name):
            node["kind"] = JOB_KINDS[name]
        if JOB_ICONS.get(name):
            node["icon"] = JOB_ICONS[name]
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
        "groups": [g for g in (
            {"label": "Run by Tollgate", "kind": "neutral", "icon": "workflow",
             "nodes": [j["name"] for j in jobs if j["kind"] or _started_by_dispatch(j, jobs)]},
            {"label": "On every pull request", "kind": "neutral", "icon": "pull-request",
             "nodes": [j["name"] for j in jobs if not j["kind"] and j["name"] not in
                       {n for x in jobs if x["kind"] for n in [x["name"]]}
                       and not _started_by_dispatch(j, jobs)]},
        ) if g["nodes"]],
    }


def icons_sheet(theme: str) -> str:
    """Every icon in diagram/icons.py, large, with its name: a reference for writers."""
    from xml.sax.saxutils import escape

    from diagram.icons import ICONS, icon
    c = THEMES[theme]
    per_row, cw, ch, pad = 6, 128, 112, 24
    rows = -(-len(ICONS) // per_row)
    w, h = per_row * cw + 2 * pad, rows * ch + 2 * pad
    out = [(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
           f'height="{h}" role="img" aria-labelledby="title desc" font-family="{MONO}">'),
           "<title id=\"title\">Tollgate's icons</title>",
           (f'<desc id="desc">Every icon in diagram/icons.py, with its name: '
           f'{escape(", ".join(ICONS))}.</desc>'),
           f'<rect width="{w}" height="{h}" fill="{c["page"]}"/>']
    for i, name in enumerate(ICONS):
        x, y = pad + (i % per_row) * cw, pad + (i // per_row) * ch
        out.append(f'<rect x="{x + 6}" y="{y + 6}" width="{cw - 12}" height="{ch - 12}" rx="6" '
                   f'fill="{c["kinds"]["neutral"][1]}" stroke="{c["border"]}"/>')
        out.append(icon(name, x + cw / 2 - 20, y + 22, 40, c["text"], 2))
        out.append(f'<text x="{x + cw / 2}" y="{y + 86}" text-anchor="middle" font-size="12" '
                   f'fill="{c["sub"]}">{escape(name)}</text>')
    return "\n".join([*out, "</svg>"]) + "\n"


GENERATED = {"workflow": workflow_spec}
# Drawn by hand in code, not from a spec.
ART = {"hero": hero.draw, "icons": icons_sheet}


def build(check=False) -> list:
    """Draw every diagram: the specs in src/, the ones from the code, and the art."""
    extra = {name: (lambda theme, make=make: draw(make(), theme)) for name, make in GENERATED.items()}
    extra.update(ART)
    return build_folder(str(HERE), check, extra)


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
