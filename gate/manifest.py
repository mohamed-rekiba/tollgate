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

A Go test file's new tests may call a seam that the builder adds. Then their package
does not compile before the build, and the report has no test of it (see not_built).
The lock names those tests by the package's import path and counts them as failing.
The gate requires each of them to run and pass on each try, as it does any locked test.

The same build failure stops an old test of that compile unit, such as one that keeps
behavior, from running. The store then runs the tests at the start, and the lock takes
such a test from that report (see claim and kept_at_start).
"""

import ast
import json
import re
from pathlib import PurePosixPath

from gate import junit
from gate.checks import only_missing_seams
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


# A Go test function: Test, Fuzz, or Example, then a name that does not start in lower
# case. TestMain runs the tests of a package and is no test of its own.
GO_TEST = re.compile(r"^func\s+((?:Test|Fuzz|Example)(?![a-z])\w*)\s*\(", re.MULTILINE)


def go_tests(data: bytes | None) -> set:
    """The names of the test functions in a Go file. An empty set for a missing file."""
    if data is None:
        return set()
    return set(GO_TEST.findall(data.decode(errors="replace"))) - {"TestMain"}


def defined_tests(repo, commit: str | None, path: str) -> set:
    """The names of the test functions in a Python or Go file at a commit."""
    if not commit:
        return set()
    data = show_bytes(repo, commit, path)
    return go_tests(data) if path.endswith(".go") else set(python_tests(data))


def go_defined(repo, commit: str, paths: list) -> dict:
    """{Go test file: the names of its test functions at the commit}, for junit.in_files."""
    return {p: go_tests(show_bytes(repo, commit, p)) for p in paths if p.endswith("_test.go")}


BUILD_FAILED = re.compile(r"^FAIL\s+(\S+) \[build failed\]", re.MULTILINE)


def not_built(repo, commit: str, ticket, test_results: dict, start: str | None,
              output: str) -> dict:
    """{test id: a failed junit.TestResult} for each test of the ticket in a Go test file
    whose package did not compile before the build, only because a new test calls a seam
    the builder adds. The id is `<import path>::<name>`, as the report names it after
    the build. The ticket's tests of a file are those the map names for it, and its new
    tests that carry an item in their name.

    A file counts only when all of these hold: the package of the file's folder failed
    to build, as a failed `<import path>::TestMain` in the report or a line `FAIL
    <import path> [build failed]` in the output (gotestsum v1.13 writes such a package
    as an empty test suite), and the report has no other test of that package;
    the file has at least one test of the ticket; each one is defined in the file and was
    not there at the start; and each line of the test check's output that names a file
    of the folder is a compile error about a seam's name (checks.only_missing_seams). A
    test that keeps behavior must pass, so one that cannot compile is refused later."""
    found = {}
    mapped = read_map(repo, commit, ticket.id)
    for path in test_files(ticket, mapped):
        if not path.endswith("_test.go"):
            continue
        failed_main = {t for t, r in test_results.items() if t.endswith("::TestMain")
                       and r.status == "failed"}
        builds = {t.split("::")[0] for t in failed_main
                  if junit.in_package(t.split("::")[0], path)}
        builds |= {p for p in BUILD_FAILED.findall(output or "") if junit.in_package(p, path)}
        if len(builds) != 1:
            continue
        package = builds.pop()
        if any(t.split("::")[0] == package for t in test_results if t not in failed_main):
            continue
        now, before = defined_tests(repo, commit, path), defined_tests(repo, start, path)
        named = sorted(n for n in now - before if ticket.item(item_of_test(n) or ""))
        names = list(dict.fromkeys([*(e["name"] for e in mapped if e["file"] == path), *named]))
        if not names or any(n not in now or n in before for n in names):
            continue
        folder = str(PurePosixPath(path).parent) + "/"
        if not only_missing_seams(output, [folder], ticket.seams):
            continue
        for name in names:
            test_id = f"{package}::{name}"
            found[test_id] = junit.TestResult(test_id, "failed", "")
    return found


def check_kept(repo, commit: str, start: str, paths: list, mapped: list) -> None:
    """Refuse a change to a test that was there at the start, and a mapped test that is
    neither there at the start nor named for its item. A file whose language has an entry
    in TEST_SOURCES is read test by test: new tests may go next to the old ones. A file
    with no entry that was there at the start must stay as it was, whole."""
    before_all = {}
    for path in paths:
        old_bytes = show_bytes(repo, start, path)
        sources = TEST_SOURCES.get(PurePosixPath(path).suffix)
        if sources is None:
            if old_bytes is not None and show_bytes(repo, commit, path) != old_bytes:
                raise FreezeError(f"{path} was there at the start, and it changed. Tollgate "
                                  "cannot read its tests one by one, so leave the file as it "
                                  "is, and put new tests in a new file")
            continue
        before = sources(old_bytes)
        now = sources(show_bytes(repo, commit, path))
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


class KeptNotRunError(FreezeError):
    """A mapped test that keeps behavior did not run with the new tests, and the caller
    passed no report of the start. The store then runs the tests at the start."""


# A line that starts a new top-level declaration of a Go file.
GO_TOP = re.compile(r"^(?:func|type|var|const|import)\b", re.MULTILINE)


def go_test_sources(data: bytes | None) -> dict:
    """{test name: its source} for each test function of a Go file: from its `func` line
    to the next top-level declaration or the end of the file, less the blank and comment
    lines at its end, which belong to the next declaration. A raw string that holds a line
    `}` does not end it early."""
    if data is None:
        return {}
    text = data.decode(errors="replace")
    found = {}
    for match in GO_TEST.finditer(text):
        end = GO_TOP.search(text, match.end())
        lines = text[match.start():end.start() if end else len(text)].splitlines()
        while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("//")):
            lines.pop()
        found[match.group(1)] = "\n".join(lines)
    return found


# The source of each test function of a test file, by the file's suffix: {name: source}.
# A language plugs in here with a function from the file's bytes to that dict. A file of
# another language has no such function, so a test file of it that was there at the
# start must stay unchanged, whole.
TEST_SOURCES = {".py": python_tests, ".go": go_test_sources}


def unchanged_test(repo, start: str, commit: str, path: str, name: str) -> bool:
    """True when the test `name` of a file has the same source at the start and at the
    commit. For a file with no entry in TEST_SOURCES, the whole file must be the same."""
    before, now = show_bytes(repo, start, path), show_bytes(repo, commit, path)
    sources = TEST_SOURCES.get(PurePosixPath(path).suffix)
    if sources is None:
        return before is not None and before == now
    old = sources(before).get(name)
    return old is not None and old == sources(now).get(name)


def claim(repo, commit: str, ticket, test_results: dict, start: str | None = None,
          start_results: dict | None = None) -> dict:
    """{test id: item id} for each test of the report that the ticket claims: a test of
    the ticket's test files that maps to a checklist item by its name or by the map.
    Raise FreezeError when the report has no test of those files, or a file has no test
    that maps to an item.

    In a compiled language, the new tests of a ticket may stop a mapped test that keeps
    behavior from building, when both are in one compile unit, such as a Go package.
    Then it cannot run before the build. start_results is the report of the tests at the
    start, the code before the new tests: a mapped test that keeps behavior and is not
    in test_results is taken from it, when its source is the same at the start and at
    the commit. With no start_results, such a test raises KeptNotRunError."""
    mapped = read_map(repo, commit, ticket.id)
    paths = test_files(ticket, mapped)
    defined = go_defined(repo, commit, paths)
    mine = {tid: r for tid, r in test_results.items() if junit.in_files(r, paths, defined)}
    if not mine:
        raise FreezeError("the test report has no test from the ticket's test files")
    items, at_start = {}, {}
    for entry in mapped:
        found = [t for t, r in mine.items() if t.split("::")[-1] == entry["name"]
                 and junit.in_files(r, [entry["file"]], defined)]
        item = ticket.item(entry["item"])
        if not found and item is not None and item.keeps_behavior and start:
            if start_results is None:
                raise KeptNotRunError(f"{entry['file']}::{entry['name']} is mapped to "
                                      f"{entry['item']}, but it did not run")
            then = go_defined(repo, start, [entry["file"]])
            found = [t for t, r in start_results.items() if t.split("::")[-1] == entry["name"]
                     and junit.in_files(r, [entry["file"]], then)]
            if found and not unchanged_test(repo, start, commit, entry["file"], entry["name"]):
                raise FreezeError(f"{entry['file']}::{entry['name']} was there at the start, "
                                  "and it changed. Leave existing tests as they are")
            at_start.update({t: start_results[t] for t in found})
            if not found:
                raise FreezeError(f"{entry['file']}::{entry['name']} is mapped to "
                                  f"{entry['item']}, but it did not run, with the new tests "
                                  "or at the start")
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
    old = {path: defined_tests(repo, start, path) for path in paths}
    for test_id, result in mine.items():
        was_there = any(test_id.split("::")[-1] in names
                        and junit.in_files(result, [path], defined)
                        for path, names in old.items())
        if test_id not in items and not was_there and ticket.item(item_of_test(test_id) or ""):
            items[test_id] = item_of_test(test_id)
    for path in paths:
        in_file = [t for t, r in mine.items() if junit.in_files(r, [path], defined)]
        if in_file and not any(t in items for t in in_file):
            raise FreezeError(f"{in_file[0]} names no checklist item, such as c1_ in its name,"
                              f" and no test of {path} is in the test map")
    return {t: items[t] for t in sorted({*mine, *at_start}) if t in items}


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
          tests_failed: bool = False, output: str = "", start_results: dict | None = None) -> dict:
    """Return the manifest for a ticket at a commit.

    test_results maps a test id to a junit.TestResult from a run of the tests
    at that commit, before any code is built. start is the commit the ticket
    started from: its tests must be kept as they were. tests_failed is True when the
    test command ended with an error.

    When the tests could not start at all (see failed_at_setup), the manifest has no
    test ids and `failed_at_setup` is true. The gate then takes the locked tests from
    the report of each try: the tests of the locked files that the ticket claims.

    output is the test check's output. When a Go package of a locked test file did not
    compile only for a seam the builder adds (see not_built), its mapped tests count as
    failing, and the manifest lists them under `not_built` as well as under `tests`.

    start_results is the report of the tests at the start (see claim). A test that keeps
    behavior and ran only there must have passed there; the manifest lists it under
    `kept_at_start` as well as under `tests` and `keeps_behavior`, so the gate requires
    it to pass after the build.
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
    late = not_built(repo, commit, ticket, test_results, start, output)
    test_results = {**test_results, **late}
    items = claim(repo, commit, ticket, test_results, start, start_results)
    at_start = sorted(t for t in items if t not in test_results)
    tests, keeps = [], []
    for test_id, item_id in items.items():
        result = test_results.get(test_id) or start_results[test_id]
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
    built = {
        "ticket": ticket.id,
        "commit": commit,
        "files": files,
        "tests": tests,
        "keeps_behavior": keeps,
        "items": items,
    }
    if late:
        built["not_built"] = sorted(t for t in late if t in items)
    if at_start:
        built["kept_at_start"] = at_start
    return built


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

