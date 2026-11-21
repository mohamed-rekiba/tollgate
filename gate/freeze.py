"""Build the lock of a ticket, and find and read the locks in the state folder.

`Store.freeze` runs the ticket's tests once, before any code is built, and
passes the results here. This module reads files only as they are in git. It
runs none of the project's code.

A ticket has at most MAX_FREEZES locks. The current lock is always
locks/<ticket>.json. When a second lock replaces it, the first one moves to
locks/replaced/<ticket>.json.
"""

import hashlib
import re
from pathlib import Path

from gate import junit, sign, state, tickets
from gate import manifest as mf
from gate.gitio import show_bytes
from gate.paths import matches

TICKET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_FREEZES = 2
NAMESPACE = "tollgate-lock"


def check_id(ticket_id: str) -> None:
    if not TICKET_ID.match(ticket_id or ""):
        raise mf.FreezeError(f"not a valid ticket id: {ticket_id!r}")


def lock_path(project, ticket_id: str) -> Path:
    """The path of the current lock of a ticket."""
    check_id(ticket_id)
    return state.path(str(project), "locks", f"{ticket_id}.json")


def replaced_path(project, ticket_id: str) -> Path:
    """The path of the lock that the second lock replaced."""
    check_id(ticket_id)
    folder = state.path(str(project), "locks", "replaced")
    folder.mkdir(exist_ok=True)
    return folder / f"{ticket_id}.json"


def next_number(project, ticket_id: str) -> int:
    """The number of the next lock of a ticket: 1, then 2."""
    return 1 + lock_path(project, ticket_id).exists() + replaced_path(project, ticket_id).exists()


def read_lock(project, ticket_id: str, signers: list) -> dict | None:
    """The verified current lock of a ticket, or None when it has none.
    Raise SignError when the lock is there but does not verify."""
    path = lock_path(project, ticket_id)
    if not path.exists():
        return None
    return sign.read(path, NAMESPACE, signers)


def lock_sha256(project, ticket_id: str) -> str | None:
    """The sha256 of the exact bytes of a ticket's current lock, as a pass record holds it."""
    path = lock_path(project, ticket_id)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def ticket_at(repo, commit: str, ticket_id: str):
    """The ticket as it is in a commit. Raise FreezeError when it is missing or names another id."""
    data = show_bytes(repo, commit, mf.ticket_path(ticket_id))
    if data is None:
        raise mf.FreezeError(f"{mf.ticket_path(ticket_id)} is not in commit {commit}")
    ticket = tickets.parse(data.decode())
    if ticket.id != ticket_id:
        raise mf.FreezeError(f"the ticket file names {ticket.id}, not {ticket_id}")
    return ticket


def check_guarded(ticket, settings: dict) -> None:
    """Refuse a ticket that would lock harness or a tier 3 or 4 path as its tests."""
    guarded = settings["harness"] + settings["tiers"]["3"] + settings["tiers"]["4"]
    for path in ticket.tests:
        if matches(path, guarded):
            raise mf.FreezeError(f"{path} is harness or a tier 3 or 4 path, so it cannot be locked")


def record(repo, ticket_id: str, commit: str, base_commit: str, settings: dict, tests: dict,
           number: int) -> dict:
    """Return the lock record of a ticket at a commit, without its time.

    tests maps a test id to {"status", "file"}, from one run of the tests at
    that commit with the harness of base_commit. Raise FreezeError when the
    ticket cannot be locked.
    """
    check_id(ticket_id)
    if number > MAX_FREEZES:
        raise mf.FreezeError(f"ticket {ticket_id} already has {MAX_FREEZES} freezes")
    ticket = ticket_at(repo, commit, ticket_id)
    check_guarded(ticket, settings)
    found = {i: junit.TestResult(i, r["status"], r.get("file", "")) for i, r in tests.items()}
    built = mf.build(repo, commit, ticket, found)
    return {
        "ticket": ticket_id,
        "base_commit": base_commit,
        "commit": commit,
        "manifest": {k: built[k] for k in ("files", "tests", "keeps_behavior")},
        "number": number,
    }
