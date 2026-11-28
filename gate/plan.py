"""Read and check a plan: .tollgate/plans/<task id>.md.

A plan has a header between two --- lines, like a ticket, and eight sections:

    ---
    id: retries
    tickets: T-1, T-2
    ---
    ## Task          what was asked, in the asker's words
    ## Design        the approach, in a few paragraphs
    ## Files         every file that changes, one per line: create, modify, or
                     delete, then the path
    ## Seams         every seam that a test observes, one per line
    ## Reuse         the code the plan uses as it is, one per line
    ## Risks         edge cases, failures, security, speed, and what must keep
                     working, one per line
    ## Assumptions   "none", or one assumption per line, asked as a question for
                     the advisor to answer
    ## Tickets       one line for each ticket id, in build order, with one sentence

Each ticket in the header has a file .tollgate/tickets/<id>/ticket.md whose
header names this plan.
"""

import re
from dataclasses import dataclass, field

from gate.tickets import TicketError
from gate.tickets import parse as parse_ticket

PLANS = ".tollgate/plans"
SECTIONS = ("Task", "Design", "Files", "Seams", "Reuse", "Risks", "Assumptions", "Tickets")
ACTIONS = ("create", "modify", "delete")
KEYS = {"id", "tickets"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    id: str
    tickets: list
    sections: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)       # path -> create, modify, or delete
    assumptions: list = field(default_factory=list)  # each asks the advisor a question


def plan_path(task_id: str) -> str:
    return f"{PLANS}/{task_id}.md"


def parse(text: str) -> Plan:
    lines = text.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        raise PlanError("a plan starts with a --- line")
    try:
        end = lines.index("---", 1)
    except ValueError:
        raise PlanError("the plan header has no closing --- line") from None
    header = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key = key.strip()
        if not sep or key not in KEYS:
            raise PlanError(f"unknown header line: {line!r}")
        header[key] = value.strip()
    if not ID.match(header.get("id", "")):
        raise PlanError("the plan header needs a valid id")
    # A list written as [a, b] is read like a, b: a common way to write a list.
    listed = header.get("tickets", "").strip().removeprefix("[").removesuffix("]")
    tickets = [t.strip().strip("'\"") for t in listed.split(",") if t.strip()]
    if not tickets:
        raise PlanError("the plan lists no tickets")
    if len(set(tickets)) != len(tickets):
        raise PlanError("the plan lists a ticket twice")
    for t in tickets:
        if not ID.match(t):
            raise PlanError(f"not a valid ticket id: {t!r}")
    sections, current = {}, None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)
    missing = [s for s in SECTIONS if not "".join(sections.get(s, [])).strip()]
    if missing:
        raise PlanError(f"the plan has empty or missing sections: {', '.join(missing)}")
    listed = " ".join(sections["Tickets"])
    for t in tickets:
        if t not in listed:
            raise PlanError(f"the Tickets section does not describe {t}")
    return Plan(header["id"], tickets, {k: "\n".join(v).strip() for k, v in sections.items()},
                _files(sections["Files"]), _assumptions(sections["Assumptions"]))


def _items(lines: list) -> list:
    return [line.strip().removeprefix("- ").strip() for line in lines if line.strip()]


def _files(lines: list) -> dict:
    files = {}
    for item in _items(lines):
        action, _, path = item.partition(" ")
        if action not in ACTIONS or not path.strip():
            raise PlanError(f"a line in Files starts with create, modify, or delete: {item}")
        files[path.strip()] = action
    return files


def _assumptions(lines: list) -> list:
    items = _items(lines)
    if [i.lower().rstrip(".") for i in items] == ["none"]:
        return []
    for item in items:
        if not item.endswith("?"):
            raise PlanError(f"each assumption must end with a question mark: {item}")
    return items


def ticket_plan(text: str) -> str:
    """The `plan:` of a ticket's header, or "". It reads only the header, so a ticket that
    breaks another rule of the format still names its plan."""
    lines = text.strip().splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() == "plan":
            return value.strip()
    return ""


def stray_tickets(plan: Plan, read, paths: list) -> list:
    """The ids of the tickets among paths, files .tollgate/tickets/<id>/ticket.md, that
    name this plan but are not in its header. read(path) returns a file's text or None."""
    found = []
    for path in paths:
        parts = path.split("/")
        if len(parts) != 4 or parts[:2] != [".tollgate", "tickets"] or parts[3] != "ticket.md":
            continue
        text = read(path)
        if parts[2] not in plan.tickets and text is not None and ticket_plan(text) == plan.id:
            found.append(parts[2])
    return found


def check_tickets(plan: Plan, read) -> list:
    """read(path) returns the text of a file or None. Return a list of problems."""
    problems = []
    for tid in plan.tickets:
        text = read(f".tollgate/tickets/{tid}/ticket.md")
        if text is None:
            problems.append(f"ticket {tid} has no file")
            continue
        try:
            ticket = parse_ticket(text)
        except TicketError as err:
            problems.append(f"ticket {tid}: {err}")
            continue
        if ticket.id != tid:
            problems.append(f"the file of ticket {tid} names {ticket.id}")
        if ticket.plan != plan.id:
            problems.append(f"ticket {tid} names plan {ticket.plan}, not {plan.id}")
    return problems
