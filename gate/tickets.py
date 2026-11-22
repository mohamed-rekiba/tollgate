"""Read and check a ticket file.

A ticket file has a header and a body. The header sits between two lines of
three dashes and holds one `key: value` per line. A list is written with
commas. The keys are `id`, `plan`, `seams`, `tests`, and `fixes`, which is
optional and names the bug the ticket fixes in one line. The body has four
sections: Current behavior, Desired behavior, Checklist, and Out of scope, and
an optional fifth, Not covered.

A checklist holds 3 to 10 items. A checklist line looks like
`- [C1, must, happy] text` or `- [C2, edge] text`. The marks inside the
brackets are the item id, then `must` and `keeps behavior` when they apply,
and at most one kind of test from KINDS.

Each kind is marked on some item, or listed under Not covered with a reason,
one line for each kind: `- concurrency: one delivery runs at a time.` A kind
cannot be both. A ticket with an item that is not `keeps behavior` needs a
`happy` item and an `error` item, and a ticket with `fixes` needs a
`regression` item: these cannot go under Not covered. The text of a
`performance` or `concurrency` item holds a number, such as a time, a count, or
a size, so that a test can fail.
"""

import re
from dataclasses import dataclass, field

SECTIONS = ("Current behavior", "Desired behavior", "Checklist", "Out of scope")
HEADER_KEYS = {"id", "plan", "seams", "tests", "fixes"}
LIST_KEYS = {"seams", "tests"}
ITEM = re.compile(r"^- \[(C\d+)((?:,[ \t]*[a-z][a-z0-9 ]*)*)\]\s+(.+)$")
KINDS = ("happy", "edge", "boundary", "error", "regression", "integration", "e2e", "security",
         "performance", "concurrency")
NUMBERED_KINDS = {"performance", "concurrency"}
NOT_COVERED = "Not covered"
NOT_COVERED_LINE = re.compile(r"^- ([a-z0-9]+):(.*)$")
NO_KINDS = ("the ticket marks no kinds of test: mark items such as [C1, must, happy] and list"
            " kinds that do not apply under ## Not covered")


class TicketError(ValueError):
    """The ticket file breaks a rule. The message names the rule."""


@dataclass
class Item:
    id: str
    text: str
    must: bool = False
    keeps_behavior: bool = False
    kind: str | None = None


@dataclass
class Ticket:
    id: str
    plan: str
    seams: list
    tests: list
    items: list = field(default_factory=list)
    sections: dict = field(default_factory=dict)
    fixes: str = ""
    not_covered: dict = field(default_factory=dict)

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
        item_id = match.group(1)
        marks = {m.strip() for m in match.group(2).split(",") if m.strip()}
        unknown = marks - {"must", "keeps behavior"} - set(KINDS)
        if unknown:
            raise TicketError(f"unknown mark on {item_id}: {min(unknown)}")
        kinds = sorted(marks & set(KINDS))
        if len(kinds) > 1:
            raise TicketError(f"{item_id} has two kinds of test: {kinds[0]} and {kinds[1]}")
        items.append(Item(item_id, match.group(3).strip(), "must" in marks,
                          "keeps behavior" in marks, kinds[0] if kinds else None))
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        raise TicketError("two checklist items have the same id")
    if not 3 <= len(items) <= 10:
        raise TicketError(f"the checklist needs 3 to 10 items, not {len(items)}")
    if not any(i.must for i in items):
        raise TicketError("the checklist needs at least one must-have item")
    for item in items:
        if item.keeps_behavior and not item.must:
            raise TicketError(f"{item.id} keeps behavior, so it must be a must-have item")
    not_covered = check_kinds(items, sections.get(NOT_COVERED, []), header.get("fixes", ""))
    return Ticket(
        id=header["id"],
        plan=header.get("plan", ""),
        seams=header.get("seams", []),
        tests=header["tests"],
        items=items,
        sections={k: "\n".join(v).strip() for k, v in sections.items()},
        fixes=header.get("fixes", ""),
        not_covered=not_covered,
    )


def check_kinds(items: list, lines: list, fixes: str) -> dict:
    """Check that each kind of test is marked or not covered. Return {kind: reason}."""
    marked = {i.kind for i in items if i.kind}
    if not marked:
        raise TicketError(NO_KINDS)
    for item in items:
        if item.kind in NUMBERED_KINDS and not re.search(r"\d", item.text):
            raise TicketError(f"{item.id} is a {item.kind} item, so its text needs a number,"
                              " such as a time, a count, or a size")
    not_covered = {}
    for line in lines:
        if not line.strip():
            continue
        match = NOT_COVERED_LINE.match(line.strip())
        if not match:
            raise TicketError(f"a Not covered line must look like '- concurrency: reason': {line}")
        kind, reason = match.group(1), match.group(2).strip()
        if kind not in KINDS:
            raise TicketError(f"unknown kind under Not covered: {kind}")
        if kind in not_covered:
            raise TicketError(f"{kind} is under Not covered twice")
        if not reason:
            raise TicketError(f"{kind} under Not covered needs a reason")
        if kind in marked:
            raise TicketError(f"{kind} is marked on an item, so it cannot be under Not covered")
        not_covered[kind] = reason
    required = []
    if any(not i.keeps_behavior for i in items):
        required += ["happy", "error"]
    if fixes:
        required.append("regression")
    for kind in required:
        if kind not in marked:
            article = "an" if kind[0] in "aeiou" else "a"
            raise TicketError(f"the ticket needs {article} {kind} item: {kind} cannot be under"
                              " Not covered")
    missing = [k for k in KINDS if k not in marked and k not in not_covered]
    if missing:
        raise TicketError(f"the ticket does not cover {', '.join(missing)}: mark an item with each,"
                          " or list it under ## Not covered with a reason")
    return not_covered
