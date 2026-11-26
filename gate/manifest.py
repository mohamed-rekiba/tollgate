"""Build and check a manifest: the record of a freeze.

The store puts the manifest in the lock, locks/<ticket>.json in the state folder.

A test belongs to a checklist item by its name, such as test_c2_ for C2, or by
the test map: .tollgate/tickets/<ticket>/tests.json, a JSON list of
{"item", "file", "name"} that the driver writes from the test writer's answer.
The map lets an existing test cover an item under its own name. The map and
each test file are locked whole. A test that maps to no item is not one of the
ticket's tests, but a test file none of whose tests maps to an item is refused.

A test that was in a test file at the ticket's start stays as it was: the freeze
refuses one whose source changed, or that is gone or renamed. New tests may go
next to it. A mapped test that is not there at the start must carry its item
in its name, as a new test does. Only a new test maps by its name: one that was
there at the start, such as an earlier ticket's test_c1_, counts only through
the map.
"""

import ast
import json
from pathlib import PurePosixPath

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
    for e in found:
        parts = PurePosixPath(e["file"]).parts
        if e["file"].startswith("/") or ".." in parts or parts[:1] == (".tollgate",):
            raise FreezeError(f"{map_path(ticket_id)} names a file outside the project's "
                              f"tests: {e['file']}")
    return found


def test_files(ticket, mapped: list) -> list:
    """The ticket's test files: those under tests:, then each other file the map names.
    The test writer cannot change the ticket, so the map may add a file."""
    return list(dict.fromkeys([*ticket.tests, *(e["file"] for e in mapped)]))


def python_tests(data: bytes | None) -> dict:
    """{test name: the test's source, as its syntax tree} for each test function in a
    Python file, in a class or not. {} for a file that is missing or does not parse."""
    if data is None:
        return {}
    try:
        tree = ast.parse(data.decode())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return {}
    return {n.name: ast.dump(n) for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef) and n.name.startswith("test")}


def check_kept(repo, commit: str, start: str, paths: list, mapped: list) -> None:
    """Refuse a change to a test that was there at the start, and a mapped test that is
    neither there at the start nor named for its item."""
    before_all = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        before = python_tests(show_bytes(repo, start, path))
        now = python_tests(show_bytes(repo, commit, path))
        before_all[path] = before
        for name, source in sorted(before.items()):
            if name not in now:
                raise FreezeError(f"{path}::{name} was there at the start, and it was removed "
                                  "or renamed. Leave existing tests as they are")
            if now[name] != source:
                raise FreezeError(f"{path}::{name} was there at the start, and it changed. "
                                  "Leave existing tests as they are")
    for entry in mapped:
        if entry["file"].endswith(".py") and entry["name"] not in before_all.get(entry["file"], {}) \
                and item_of_test(entry["name"]) != entry["item"]:
            raise FreezeError(f"{entry['file']}::{entry['name']} is mapped to {entry['item']}, "
                              f"but it was not there at the start, so it must be a new test "
                              f"named for its item, such as test_{entry['item'].lower()}_")


def claim(repo, commit: str, ticket, test_results: dict, start: str | None = None) -> dict:
    """{test id: item id} for each test of the report that the ticket claims: a test of
    the ticket's test files that maps to a checklist item by its name or by the map.
    Raise FreezeError when the report has no test of those files, or a file has no test
    that maps to an item."""
    mapped = read_map(repo, commit, ticket.id)
    paths = test_files(ticket, mapped)
    mine = {tid: r for tid, r in test_results.items() if junit.in_files(r, paths)}
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
    if start:
        check_kept(repo, commit, start, paths, mapped)
    # A test that was there at the start, such as an earlier ticket's test_c1_, maps
    # only through the map: only a new test maps by its name.
    old = {path: python_tests(show_bytes(repo, start, path)) if start else {}
           for path in paths}
    for test_id, result in mine.items():
        was_there = any(test_id.split("::")[-1] in names and junit.in_files(result, [path])
                        for path, names in old.items())
        if test_id not in items and not was_there and ticket.item(item_of_test(test_id) or ""):
            items[test_id] = item_of_test(test_id)
    for path in paths:
        in_file = [t for t, r in mine.items() if junit.in_files(r, [path])]
        if in_file and not any(t in items for t in in_file):
            raise FreezeError(f"{in_file[0]} names no checklist item, such as c1_ in its name,"
                              f" and no test of {path} is in the test map")
    return {t: items[t] for t in sorted(mine) if t in items}


def missing_items(ticket, items: dict) -> list:
    """The must-have items that no claimed test covers."""
    covered = set(items.values())
    return [i.id for i in ticket.items if i.must and i.id not in covered]


def failed_at_setup(repo, ticket, paths: list, test_results: dict, start: str | None,
                    tests_failed: bool) -> bool:
    """True when the tests could not start before the build, and that still counts as the
    locked tests failing: every locked test file is new, so no test of it was there to run,
    the report lists no test at all, and the test command ended with an error. In a new
    project the first ticket may write the build file, such as go.mod: until then the
    test command fails at its setup and writes no report. A ticket that keeps behavior
    needs its tests to pass before the build, so it cannot be locked this way."""
    if test_results or not tests_failed or not start or not paths:
        return False
    if any(show_bytes(repo, start, path) is not None for path in paths):
        return False
    return not any(i.keeps_behavior for i in ticket.items if i.must)


def build(repo, commit: str, ticket, test_results: dict, start: str | None = None,
          tests_failed: bool = False) -> dict:
    """Return the manifest for a ticket at a commit.

    test_results maps a test id to a junit.TestResult from a run of the tests
    at that commit, before any code is built. start is the commit the ticket
    started from: its tests must be kept as they were. tests_failed is True when the
    test command ended with an error.

    When the tests could not start at all (see failed_at_setup), the manifest has no
    test ids and `failed_at_setup` is true. The gate then takes the locked tests from
    the report of each try: the tests of the locked files that the ticket claims.
    """
    mapped = read_map(repo, commit, ticket.id)
    paths = test_files(ticket, mapped)
    files = {}
    for path in [ticket_path(ticket.id), *paths] + ([map_path(ticket.id)] if mapped else []):
        data = show_bytes(repo, commit, path)
        if data is None:
            raise FreezeError(f"{path} is not in commit {commit}")
        files[path] = fingerprint(data)
    if failed_at_setup(repo, ticket, paths, test_results, start, tests_failed):
        return {"ticket": ticket.id, "commit": commit, "files": files, "tests": [],
                "keeps_behavior": [], "items": {}, "failed_at_setup": True}
    items = claim(repo, commit, ticket, test_results, start)
    tests, keeps = [], []
    for test_id, item_id in items.items():
        result = test_results[test_id]
        item = ticket.item(item_id)
        if result.status == "skipped":
            raise FreezeError(f"{test_id} was skipped")
        if item.keeps_behavior:
            if result.status != "passed":
                raise FreezeError(f"{test_id} keeps behavior, so it must pass before the build")
            keeps.append(test_id)
        elif result.status == "passed":
            raise FreezeError(f"{test_id} passed before the build, so it tests nothing new")
        tests.append(test_id)
    missing = missing_items(ticket, items)
    if missing:
        raise FreezeError(f"must-have items with no test: {', '.join(missing)}")
    return {
        "ticket": ticket.id,
        "commit": commit,
        "files": files,
        "tests": tests,
        "keeps_behavior": keeps,
        "items": items,
    }


def after_setup(repo, lock: dict, ticket, test_results: dict) -> dict:
    """{test id: item id}: the locked tests of a lock made when the tests could not start
    before the build, as the report of a try lists them. Raise FreezeError when the report
    has none, or a must-have item has no test."""
    items = claim(repo, lock["commit"], ticket, test_results, lock.get("base_commit"))
    missing = missing_items(ticket, items)
    if missing:
        raise FreezeError(f"must-have items with no test: {', '.join(missing)}")
    return items


def changed(manifest: dict, repo, ref: str) -> list:
    """Return the frozen files that differ at ref, or are missing there."""
    out = []
    for path, print_ in sorted(manifest["files"].items()):
        data = show_bytes(repo, ref, path)
        if data is None or fingerprint(data) != print_:
            out.append(path)
    return out

