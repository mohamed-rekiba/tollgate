"""Read and check an analysis: .tollgate/analysis/<task id>.md.

The analyst writes it before the plan, from the code alone. It has a header and
six sections, and each fact is one line that is confirmed or assumed:

    ---
    task: retries
    commit: 3d549d7
    ---
    ## Structure          how the project is laid out
    ## Entry points       where a run starts, and the modules that matter
    ## Frameworks         the frameworks, libraries, and patterns it uses
    ## Similar features   how the code already does something like the request
    ## Tests              the test framework and how tests are written
    ## Standards          the coding standards and instructions it follows

    - confirmed: the sender lives in one module [src/send.py:1]
    - confirmed: the handler calls it [src/web.py::deliver]
    - assumed: the project runs on Python 3.11

A confirmed fact cites the code: [path:line] or [path::name]. verify() checks
each citation against the commit the analysis read, and makes a fact whose
citation does not exist an assumption.
"""

import re
from dataclasses import dataclass, field

from gate.paths import line_exists, name_exists

ANALYSES = ".tollgate/analysis"
SECTIONS = ("Structure", "Entry points", "Frameworks", "Similar features", "Tests", "Standards")
STATUSES = ("confirmed", "assumed")
CITE = re.compile(r"\[([^\]\s:]+(?:/[^\]\s:]+)*)(?::(\d+)|::([\w.]+))\]")


class AnalysisError(ValueError):
    pass


@dataclass
class Fact:
    status: str
    text: str
    cites: list = field(default_factory=list)   # (path, line or None, name or None)


@dataclass
class Analysis:
    task: str
    commit: str
    sections: dict = field(default_factory=dict)   # section name -> [Fact]


def analysis_path(task_id: str) -> str:
    return f"{ANALYSES}/{task_id}.md"


def _cite(c) -> str:
    path, line, name = c
    return f"{path}:{line}" if line is not None else f"{path}::{name}"


def parse(text: str) -> Analysis:
    lines = text.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise AnalysisError("an analysis starts with a --- line")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise AnalysisError("the analysis header has no closing --- line") from None
    header = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            header[key.strip()] = value.strip()
    for key in ("task", "commit"):
        if not header.get(key):
            raise AnalysisError(f"the analysis header needs a {key}")
    sections, current = {}, None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        item = line.strip().removeprefix("- ").strip()
        if not item or current is None:
            continue
        status, sep, claim = item.partition(":")
        if not sep or status.strip() not in STATUSES:
            raise AnalysisError(f"each fact starts with confirmed or assumed: {item}")
        status, claim = status.strip(), claim.strip()
        cites = [(m[1], int(m[2]) if m[2] else None, m[3] or None) for m in CITE.finditer(claim)]
        if status == "confirmed" and not cites:
            raise AnalysisError(f"a confirmed fact cites no code: {claim}")
        sections[current].append(Fact(status, claim, cites))
    missing = [s for s in SECTIONS if not sections.get(s)]
    if missing:
        raise AnalysisError(f"the analysis has empty or missing sections: {', '.join(missing)}")
    return Analysis(header["task"], header["commit"], {s: sections[s] for s in SECTIONS})


def verify(analysis: Analysis, root: str) -> list:
    """Check every citation of a confirmed fact against the files under root.
    A fact with a citation that does not exist becomes assumed. Return those citations."""
    missing = []
    for facts in analysis.sections.values():
        for f in facts:
            if f.status != "confirmed":
                continue
            gone = [c for c in f.cites
                    if not (line_exists(root, c[0], c[1]) if c[1] is not None
                            else name_exists(root, c[0], c[2]))]
            if gone:
                f.status = "assumed"
                f.text += " (not found: " + ", ".join(_cite(c) for c in gone) + ")"
                missing += [_cite(c) for c in gone]
    return missing


def render(analysis: Analysis) -> str:
    out = ["---", f"task: {analysis.task}", f"commit: {analysis.commit}", "---"]
    for name, facts in analysis.sections.items():
        out.append(f"## {name}")
        out += [f"- {f.status}: {f.text}" for f in facts]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    """Check an analysis read on standard input against the project; print it checked."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(prog="python3 -m gate.analysis", description=main.__doc__)
    parser.add_argument("--root", default=".", help="the project folder")
    args = parser.parse_args(argv)
    try:
        found = parse(sys.stdin.read())
    except AnalysisError as err:
        print(f"The analysis cannot be read: {err}")
        return 1
    missing = verify(found, args.root)
    print(render(found))
    print("Every citation was found." if not missing
          else f"Not found, so made assumptions: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
