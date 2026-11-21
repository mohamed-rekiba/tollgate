"""Build, check, and read a manifest: the record of a freeze.

The manifest lives in the message of the freeze tag, as JSON.
"""

import json

from action import junit
from action.gitio import fingerprint, show_bytes
from action.tickets import item_of_test

TICKET_DIR = ".tollgate/tickets"


class FreezeError(ValueError):
    """The ticket cannot be frozen. The message says why."""


def ticket_path(ticket_id: str) -> str:
    return f"{TICKET_DIR}/{ticket_id}/ticket.md"


def build(repo, commit: str, ticket, test_results: dict) -> dict:
    """Return the manifest for a ticket at a commit.

    test_results maps a test id to a junit.TestResult from a run of the tests
    at that commit, before any code is built.
    """
    files = {}
    for path in [ticket_path(ticket.id), *ticket.tests]:
        data = show_bytes(repo, commit, path)
        if data is None:
            raise FreezeError(f"{path} is not in commit {commit}")
        files[path] = fingerprint(data)
    mine = {tid: r for tid, r in test_results.items() if junit.in_files(r, ticket.tests)}
    if not mine:
        raise FreezeError("the test report has no test from the ticket's test files")
    tests, keeps = [], []
    for test_id, result in sorted(mine.items()):
        item_id = item_of_test(test_id)
        item = ticket.item(item_id) if item_id else None
        if item is None:
            raise FreezeError(f"{test_id} names no checklist item, such as c1_ in its name")
        if result.status == "skipped":
            raise FreezeError(f"{test_id} was skipped")
        if item.keeps_behavior:
            if result.status != "passed":
                raise FreezeError(f"{test_id} keeps behavior, so it must pass before the build")
            keeps.append(test_id)
        elif result.status == "passed":
            raise FreezeError(f"{test_id} passed before the build, so it tests nothing new")
        tests.append(test_id)
    covered = {item_of_test(t) for t in tests}
    missing = [i.id for i in ticket.items if i.must and i.id not in covered]
    if missing:
        raise FreezeError(f"must-have items with no test: {', '.join(missing)}")
    return {
        "ticket": ticket.id,
        "commit": commit,
        "files": files,
        "tests": tests,
        "keeps_behavior": keeps,
        "items": {t: item_of_test(t) for t in tests},
    }


def changed(manifest: dict, repo, ref: str) -> list:
    """Return the frozen files that differ at ref, or are missing there."""
    out = []
    for path, print_ in sorted(manifest["files"].items()):
        data = show_bytes(repo, ref, path)
        if data is None or fingerprint(data) != print_:
            out.append(path)
    return out


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True)


def loads(text: str) -> dict:
    """Read a manifest from a tag message. The JSON may follow other lines."""
    start = text.find("{")
    if start < 0:
        raise FreezeError("the tag message holds no manifest")
    return json.loads(text[start : text.rfind("}") + 1])
