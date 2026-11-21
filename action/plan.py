"""Read and check a plan: .tollgate/plans/<task id>.md.

A plan has a header between two --- lines, like a ticket, and five sections:

    ---
    id: retries
    tickets: T-1, T-2
    ---
    ## Task          what was asked, in the asker's words
    ## Design        the approach, in a few paragraphs
    ## Files         every file that changes, one per line
    ## Seams         every seam that a test observes, one per line
    ## Tickets       one line for each ticket id, in build order, with one sentence

Each ticket in the header has a file .tollgate/tickets/<id>/ticket.md whose
header names this plan.
"""

import re
from dataclasses import dataclass, field

from action.tickets import TicketError
from action.tickets import parse as parse_ticket

PLANS = ".tollgate/plans"
SECTIONS = ("Task", "Design", "Files", "Seams", "Tickets")
KEYS = {"id", "tickets"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class PlanError(ValueError):
    pass


@dataclass
class Plan:
    id: str
    tickets: list
    sections: dict = field(default_factory=dict)


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
    return Plan(header["id"], tickets, {k: "\n".join(v).strip() for k, v in sections.items()})


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
