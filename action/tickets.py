"""Read and check a ticket file.

A ticket file has a header and a body. The header sits between two lines of
three dashes and holds one `key: value` per line. A list is written with
commas. The body has four sections: Current behavior, Desired behavior,
Checklist, and Out of scope.

A checklist line looks like `- [C1, must] text` or `- [C2] text`. The marks
inside the brackets are the item id, then `must` and `keeps behavior` when
they apply.
"""

import re
from dataclasses import dataclass, field

SECTIONS = ("Current behavior", "Desired behavior", "Checklist", "Out of scope")
HEADER_KEYS = {"id", "plan", "seams", "tests"}
LIST_KEYS = {"seams", "tests"}
ITEM = re.compile(r"^- \[(C\d+)((?:,\s*[a-z ]+)*)\]\s+(.+)$")


class TicketError(ValueError):
    """The ticket file breaks a rule. The message names the rule."""


@dataclass
class Item:
    id: str
    text: str
    must: bool = False
    keeps_behavior: bool = False


@dataclass
class Ticket:
    id: str
    plan: str
    seams: list
    tests: list
    items: list = field(default_factory=list)
    sections: dict = field(default_factory=dict)

    def item(self, item_id):
        return next((i for i in self.items if i.id == item_id), None)


def item_of_test(test_id: str) -> str | None:
    """Return the item id that a test name carries, such as C2 for test_c2_fails."""
    found = re.search(r"(?:^|[^a-z0-9])c(\d+)_", test_id.lower())
    return f"C{found.group(1)}" if found else None


def parse(text: str) -> Ticket:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise TicketError("the ticket must start with a header between --- lines")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise TicketError("the header has no closing --- line") from None
    header = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in HEADER_KEYS:
            raise TicketError(f"unknown header line: {line}")
        value = value.strip()
        header[key] = [v.strip() for v in value.split(",") if v.strip()] if key in LIST_KEYS else value
    for key in ("id", "tests"):
        if not header.get(key):
            raise TicketError(f"the header needs {key}")
    sections, current = {}, None
    for line in lines[end + 1 :]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    for name in SECTIONS:
        if name not in sections:
            raise TicketError(f"the ticket needs a section: {name}")
    items = []
    for line in sections["Checklist"]:
        if not line.strip():
            continue
        match = ITEM.match(line.strip())
        if not match:
            raise TicketError(f"a checklist line must look like '- [C1, must] text': {line}")
        marks = {m.strip() for m in match.group(2).split(",") if m.strip()}
        unknown = marks - {"must", "keeps behavior"}
        if unknown:
            raise TicketError(f"unknown mark on {match.group(1)}: {min(unknown)}")
        items.append(Item(match.group(1), match.group(3).strip(), "must" in marks, "keeps behavior" in marks))
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise TicketError("two checklist items have the same id")
    if not 3 <= len(items) <= 7:
        raise TicketError(f"the checklist needs 3 to 7 items, not {len(items)}")
    if not any(i.must for i in items):
        raise TicketError("the checklist needs at least one must-have item")
    for item in items:
        if item.keeps_behavior and not item.must:
            raise TicketError(f"{item.id} keeps behavior, so it must be a must-have item")
    return Ticket(
        id=header["id"],
        plan=header.get("plan", ""),
        seams=header.get("seams", []),
        tests=header["tests"],
        items=items,
        sections={k: "\n".join(v).strip() for k, v in sections.items()},
    )


def main(argv=None) -> int:
    """Check one ticket file. Print its id and items, or the error. Return 0 or 1."""
    import argparse

    ap = argparse.ArgumentParser(prog="python3 -m action.tickets", description="Check one ticket file.")
    ap.add_argument("path")
    args = ap.parse_args(argv)
    try:
        with open(args.path, encoding="utf-8") as f:
            ticket = parse(f.read())
    except (OSError, UnicodeDecodeError, TicketError) as err:
        print(f"error: {err}")
        return 1
    print(f"id: {ticket.id}")
    for item in ticket.items:
        marks = "".join(f", {m}" for m, on in (("must", item.must), ("keeps behavior", item.keeps_behavior)) if on)
        print(f"- [{item.id}{marks}] {item.text}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
