"""Build and check a manifest: the record of a freeze.

The store puts the manifest in the signed lock, locks/<ticket>.json in the state folder.

A test belongs to a checklist item by its name, such as test_c2_ for C2, or by
the test map: .tollgate/tickets/<ticket>/tests.json, a JSON list of
{"item", "file", "name"} that the driver writes from the test writer's answer.
The map lets an existing test cover an item under its own name. The map and
each test file are locked whole. A test that maps to no item is not one of the
ticket's tests, but a test file none of whose tests maps to an item is refused.
"""

import json

from gate import junit
from gate.gitio import fingerprint, show_bytes
from gate.tickets import item_of_test

TICKET_DIR = ".tollgate/tickets"


class FreezeError(ValueError):
    """The ticket cannot be frozen. The message says why."""


def ticket_path(ticket_id: str) -> str:
    return f"{TICKET_DIR}/{ticket_id}/ticket.md"


def map_path(ticket_id: str) -> str:
    return f"{TICKET_DIR}/{ticket_id}/tests.json"


def read_map(repo, commit: str, ticket_id: str) -> list:
    """The test map at a commit: [{"item", "file", "name"}], or [] when there is none."""
    data = show_bytes(repo, commit, map_path(ticket_id))
    if data is None:
        return []
    try:
        found = json.loads(data.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise FreezeError(f"{map_path(ticket_id)} is not JSON: {err}") from None
    if not isinstance(found, list) or not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) and e.get(k)
                                        for k in ("item", "file", "name")) for e in found):
        raise FreezeError(f"{map_path(ticket_id)} must be a list of "
                          '{"item", "file", "name"}')
    return found


def build(repo, commit: str, ticket, test_results: dict) -> dict:
    """Return the manifest for a ticket at a commit.

    test_results maps a test id to a junit.TestResult from a run of the tests
    at that commit, before any code is built.
    """
    mapped = read_map(repo, commit, ticket.id)
    files = {}
    for path in [ticket_path(ticket.id), *ticket.tests] + ([map_path(ticket.id)] if mapped else []):
        data = show_bytes(repo, commit, path)
        if data is None:
            raise FreezeError(f"{path} is not in commit {commit}")
        files[path] = fingerprint(data)
    mine = {tid: r for tid, r in test_results.items() if junit.in_files(r, ticket.tests)}
    if not mine:
        raise FreezeError("the test report has no test from the ticket's test files")
    items = {}
    for entry in mapped:
        found = [t for t, r in mine.items() if t.split("::")[-1] == entry["name"]
                 and junit.in_files(r, [entry["file"]])]
        if not found:
            raise FreezeError(f"{entry['file']}::{entry['name']} is mapped to {entry['item']}, "
                              "but it did not run")
        if ticket.item(entry["item"]) is None:
            raise FreezeError(f"{entry['file']}::{entry['name']} is mapped to {entry['item']}, "
                              "which is not a checklist item")
        items.update(dict.fromkeys(found, entry["item"]))
    for test_id in mine:
        if test_id not in items and ticket.item(item_of_test(test_id) or ""):
            items[test_id] = item_of_test(test_id)
    for path in ticket.tests:
        in_file = [t for t, r in mine.items() if junit.in_files(r, [path])]
        if in_file and not any(t in items for t in in_file):
            raise FreezeError(f"{in_file[0]} names no checklist item, such as c1_ in its name,"
                              f" and no test of {path} is in the test map")
    tests, keeps = [], []
    for test_id, result in sorted(mine.items()):
        if test_id not in items:
            continue    # a test of the file that the ticket does not claim
        item = ticket.item(items[test_id])
        if result.status == "skipped":
            raise FreezeError(f"{test_id} was skipped")
        if item.keeps_behavior:
            if result.status != "passed":
                raise FreezeError(f"{test_id} keeps behavior, so it must pass before the build")
            keeps.append(test_id)
        elif result.status == "passed":
            raise FreezeError(f"{test_id} passed before the build, so it tests nothing new")
        tests.append(test_id)
    covered = {items[t] for t in tests}
    missing = [i.id for i in ticket.items if i.must and i.id not in covered]
    if missing:
        raise FreezeError(f"must-have items with no test: {', '.join(missing)}")
    return {
        "ticket": ticket.id,
        "commit": commit,
        "files": files,
        "tests": tests,
        "keeps_behavior": keeps,
        "items": {t: items[t] for t in tests},
    }


def changed(manifest: dict, repo, ref: str) -> list:
    """Return the frozen files that differ at ref, or are missing there."""
    out = []
    for path, print_ in sorted(manifest["files"].items()):
        data = show_bytes(repo, ref, path)
        if data is None or fingerprint(data) != print_:
            out.append(path)
    return out

