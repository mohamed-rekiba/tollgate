"""Read and check a brief: .tollgate/briefs/<id>.md.

A brainstorm turns a rough idea into a brief, and /tollgate:task --brief <id>
takes the brief as its request. A brief has a header between two --- lines, like
a plan, and six sections:

    ---
    id: shout
    size: task                   task, or roadmap when one plan cannot hold it
    ---
    ## Overview                  the idea, in a few sentences
    ## Analysis                  what the lenses found, merged, one finding per line
    ## Goals                     what the change does, one per line
    ## Non-goals                 what it does not do, one per line
    ## Alternatives weighed      one per line: <alternative>: dropped because <reason>
    ## Open questions            "none", or one question per line, each ending with ?

Each line of a list section starts with "- ". The Analysis says each thing once.

    python3 -P -m gate.brief --project . <brief id> [--to <file>]

checks the brief, copies it to <file> when --to is given, and prints its id, its
size, and the number of open questions as JSON. It ends with 1 and says what to
fix when the brief is missing or not in this format.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BRIEFS = ".tollgate/briefs"
IDEAS = ".tollgate/ideas"
SECTIONS = ("Overview", "Analysis", "Goals", "Non-goals", "Alternatives weighed",
            "Open questions")
LISTS = SECTIONS[1:]
SIZES = ("task", "roadmap")
KEYS = {"id", "size"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DROPPED = ": dropped because "


class BriefError(ValueError):
    pass


@dataclass
class Brief:
    id: str
    size: str
    sections: dict = field(default_factory=dict)
    goals: list = field(default_factory=list)
    non_goals: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)   # (alternative, why it was dropped)
    open_questions: list = field(default_factory=list)


def brief_path(brief_id: str) -> str:
    return f"{BRIEFS}/{brief_id}.md"


def idea_path(brief_id: str) -> str:
    return f"{IDEAS}/{brief_id}.md"


def is_brief(text: str) -> bool:
    """True when the text is written as a brief, not as a plain request."""
    lines = (text or "").strip().splitlines()
    return bool(lines) and lines[0].strip() == "---" and "\n## Overview" in text


def _items(name: str, lines: list) -> list:
    items = []
    for line in lines:
        if not line.strip():
            continue
        if not line.startswith("- "):
            raise BriefError(f"each line in {name} starts with - : {line.strip()}")
        items.append(line[2:].strip())
    return items


def parse(text: str) -> Brief:
    lines = text.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise BriefError("a brief starts with a --- line")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise BriefError("the brief header has no closing --- line") from None
    header = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or key.strip() not in KEYS:
            raise BriefError(f"unknown header line: {line!r}")
        header[key.strip()] = value.strip()
    if not ID.match(header.get("id", "")):
        raise BriefError("the brief header needs a valid id")
    if header.get("size") not in SIZES:
        raise BriefError("the brief header needs size: task or size: roadmap")
    sections, current = {}, None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    missing = [s for s in SECTIONS if not "".join(sections.get(s, [])).strip()]
    if missing:
        raise BriefError(f"the brief has empty or missing sections: {', '.join(missing)}")
    none = "".join(sections["Open questions"]).strip().removeprefix("- ").lower().rstrip(".")
    items = {name: [] if name == "Open questions" and none == "none"
             else _items(name, sections[name]) for name in LISTS}
    seen = set()
    for item in items["Analysis"]:
        same = re.sub(r"\W+", " ", item).strip().lower()
        if same in seen:
            raise BriefError(f"the Analysis says the same thing twice: {item}")
        seen.add(same)
    alternatives = []
    for item in items["Alternatives weighed"]:
        what, sep, why = item.partition(DROPPED)
        if not sep or not what.strip() or not why.strip():
            raise BriefError("each line in Alternatives weighed reads "
                             f"'<alternative>: dropped because <reason>': {item}")
        alternatives.append((what.strip(), why.strip()))
    questions = items.get("Open questions", [])
    for item in questions:
        if not item.endswith("?"):
            raise BriefError(f"each open question must end with a question mark: {item}")
    return Brief(header["id"], header["size"],
                 {k: "\n".join(v).strip() for k, v in sections.items()},
                 items["Goals"], items["Non-goals"], alternatives, questions)


def load(project: str, brief_id: str) -> Brief:
    """The brief <brief_id> of the project, checked. Raise BriefError with what to fix."""
    if not ID.match(brief_id or ""):
        raise BriefError(f"not a valid brief id: {brief_id!r}")
    path = Path(project, brief_path(brief_id))
    if not path.exists():
        raise BriefError(f"there is no brief {brief_id}: {brief_path(brief_id)} does not "
                         "exist. Run /tollgate:brainstorm to write it")
    try:
        found = parse(path.read_text())
    except BriefError as err:
        raise BriefError(f"{brief_path(brief_id)} is not a valid brief: {err}") from None
    if found.id != brief_id:
        raise BriefError(f"{brief_path(brief_id)} names {found.id}, not {brief_id}")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate brief", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("brief")
    parser.add_argument("--to", help="copy the brief to this file, as the request of a task")
    args = parser.parse_args(argv)
    try:
        found = load(args.project, args.brief)
    except BriefError as err:
        print(f"tollgate brief: {err}", file=sys.stderr)
        return 1
    if args.to:
        to = Path(args.to)
        to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(Path(args.project, brief_path(args.brief)).read_text())
    print(json.dumps({"id": found.id, "size": found.size,
                      "open_questions": len(found.open_questions)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
