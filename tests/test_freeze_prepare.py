"""Tests for the freeze command and the restore step."""

import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from gate import freeze, gate, junit, prepare
from gate import manifest as mf
from gate import settings as st
from gate.checks import CheckResult, Results
from tests.helpers import TICKET, Repo, settings_text


def results_file(folder, **status):
    tests = {"test_c1_retries": "failed", "test_c2_sent_once": "passed",
             "test_c3_wait_logged": "failed"}
    tests.update(status)
    r = Results([CheckResult("tests", False)],
                {f"tests.test_t1::{n}": {"status": s, "file": ""} for n, s in tests.items()})
    path = Path(folder, "results.json")
    path.write_text(r.to_json())
    return str(path)


def results_of(path):
    return Results.from_json(Path(path).read_text()).tests


class FreezeTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json", settings_text())
        self.repo.write(mf.ticket_path("T-1"), TICKET)
        self.repo.write("tests/test_t1.py", "# tests\n")
        self.commit = self.repo.commit()
        self.settings = st.load_from_ref(str(self.repo.path), "main")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def record(self, number=1, ticket="T-1", **status):
        return freeze.record(str(self.repo.path), ticket, self.commit, "b" * 40, self.settings,
                             results_of(results_file(self.tmp.name, **status)), number)

    def test_first_lock(self):
        lock = self.record()
        self.assertEqual((lock["number"], lock["commit"], lock["base_commit"]),
                         (1, self.commit, "b" * 40))
        self.assertEqual(sorted(lock["manifest"]), ["files", "items", "keeps_behavior", "tests"])
        self.assertEqual(lock["manifest"]["keeps_behavior"], ["tests.test_t1::test_c2_sent_once"])

    def test_a_third_lock_is_refused(self):
        self.assertEqual(self.record(number=2)["number"], 2)
        with self.assertRaisesRegex(mf.FreezeError, "already has 2 freezes"):
            self.record(number=3)

    def test_refuses_a_bad_ticket_id(self):
        with self.assertRaisesRegex(mf.FreezeError, "not a valid ticket id"):
            self.record(ticket="T-1;rm")

    def test_refuses_a_test_that_passes_before_the_build(self):
        with self.assertRaisesRegex(mf.FreezeError, "passed before the build"):
            self.record(test_c1_retries="passed")



class FailedAtSetupTest(unittest.TestCase):
    """In a new project the first ticket may write the build file, such as go.mod. Before
    the build the test command then fails at its setup and writes no report."""

    NEW = TICKET.replace("[C2, must, keeps behavior, regression]", "[C2, must, regression]")

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json", settings_text())
        self.start = self.repo.commit("start")
        self.settings = st.load_from_ref(str(self.repo.path), "main")

    def lock(self, ticket=None, tests=None, failed=True, start=None):
        self.repo.write(mf.ticket_path("T-1"), ticket or self.NEW)
        self.repo.write("tests/test_t1.py", "# tests\n")
        commit = self.repo.commit("test(T-1): the ticket and its locked tests")
        return freeze.record(str(self.repo.path), "T-1", commit, start or self.start,
                             self.settings, tests or {}, 1, failed)

    def test_new_test_files_no_report_and_a_failed_command_lock_with_no_test_ids(self):
        manifest = self.lock()["manifest"]
        self.assertTrue(manifest["failed_at_setup"])
        self.assertEqual((manifest["tests"], manifest["items"]), ([], {}))
        self.assertIn("tests/test_t1.py", manifest["files"])

    def test_it_is_refused_when_any_condition_does_not_hold(self):
        no_test = "the test report has no test from the ticket's test files"
        with self.subTest("the command passed"), self.assertRaisesRegex(mf.FreezeError, no_test):
            self.lock(failed=False)
        with self.subTest("the report lists a test"), \
                self.assertRaisesRegex(mf.FreezeError, no_test):
            self.lock(tests={"other::test_x": {"status": "failed", "file": ""}})
        with self.subTest("an item keeps behavior"), \
                self.assertRaisesRegex(mf.FreezeError, no_test):
            self.lock(ticket=TICKET)

    def test_it_is_refused_when_a_locked_test_file_was_there_at_the_start(self):
        self.repo.write("tests/test_t1.py", "# an older test file\n")
        start = self.repo.commit("an older test file")
        with self.assertRaisesRegex(mf.FreezeError, "no test from the ticket's test files"):
            self.lock(start=start)

    def test_a_normal_lock_has_no_mark(self):
        tests = {f"tests.test_t1::test_c{n}_x": {"status": "failed", "file": ""}
                 for n in (1, 2, 3)}
        self.assertNotIn("failed_at_setup", self.lock(tests=tests)["manifest"])


CALC = """import unittest

import calc


class Calc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)

    def test_subtract(self):
        self.assertEqual(calc.subtract(5, 3), 2)

    def test_round(self):
        self.assertEqual(calc.round_half(2.5), 3)
"""


class TestMapTest(unittest.TestCase):
    """The test writer may point an item at an existing test, which keeps its own name."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json", settings_text())
        self.repo.write(mf.ticket_path("T-1"), TICKET.replace(
            "tests: tests/test_t1.py", "tests: tests/test_t1.py, tests/test_calc.py"))
        self.repo.write("tests/test_t1.py", "# tests\n")
        self.repo.write("tests/test_calc.py", CALC)
        self.start = self.repo.commit()
        self.settings = st.load_from_ref(str(self.repo.path), "main")

    def lock(self, mapped, **status):
        if mapped is not None:
            import json
            self.repo.write(mf.map_path("T-1"), json.dumps(mapped))
        commit = self.repo.commit()
        tests = {"tests.test_t1::test_c1_retries": "failed",
                 "tests.test_t1::test_c3_wait_logged": "failed",
                 "tests.test_calc::test_add": "passed", "tests.test_calc::test_subtract": "passed",
                 "tests.test_calc::test_round": "passed", **status}
        found = {i: {"status": s, "file": ""} for i, s in tests.items()}
        return freeze.record(str(self.repo.path), "T-1", commit, self.start, self.settings,
                             found, 1)["manifest"]

    ADD: ClassVar[dict] = {"item": "C2", "file": "tests/test_calc.py", "name": "test_add"}
    SUBTRACT: ClassVar[dict] = {"item": "C2", "file": "tests/test_calc.py",
                                "name": "test_subtract"}

    def test_an_existing_test_covers_a_keeps_behavior_item_by_the_map(self):
        manifest = self.lock([self.ADD, self.SUBTRACT])
        self.assertEqual(manifest["keeps_behavior"],
                         ["tests.test_calc::test_add", "tests.test_calc::test_subtract"])
        self.assertEqual(manifest["items"], {
            "tests.test_calc::test_add": "C2", "tests.test_calc::test_subtract": "C2",
            "tests.test_t1::test_c1_retries": "C1", "tests.test_t1::test_c3_wait_logged": "C3"})
        # The whole file is locked, with the map; its other tests are not the ticket's.
        self.assertIn("tests/test_calc.py", manifest["files"])
        self.assertIn(mf.map_path("T-1"), manifest["files"])
        self.assertNotIn("tests.test_calc::test_round", manifest["tests"])

    def test_a_file_none_of_whose_tests_maps_to_an_item_is_refused(self):
        with self.assertRaisesRegex(mf.FreezeError, "names no checklist item"):
            self.lock(None)

    def test_a_mapped_test_must_exist(self):
        with self.assertRaisesRegex(mf.FreezeError, "test_multiply.*did not run"):
            self.lock([self.ADD, dict(self.ADD, name="test_multiply")])

    def test_a_mapped_keeps_behavior_test_must_pass_and_a_new_test_must_fail(self):
        with self.assertRaisesRegex(mf.FreezeError, "keeps behavior"):
            self.lock([self.ADD], **{"tests.test_calc::test_add": "failed"})
        with self.assertRaisesRegex(mf.FreezeError, "passed before the build"):
            self.lock([self.ADD, {"item": "C1", "file": "tests/test_calc.py",
                                  "name": "test_round"}])

    def test_an_existing_test_the_test_writer_weakened_is_refused(self):
        self.repo.write("tests/test_calc.py", CALC.replace(
            "self.assertEqual(calc.add(2, 3), 5)", "self.assertTrue(True)"))
        with self.assertRaisesRegex(mf.FreezeError, "test_add.*changed"):
            self.lock([self.ADD, self.SUBTRACT])

    def test_an_existing_test_renamed_or_removed_is_refused(self):
        self.repo.write("tests/test_calc.py", CALC.replace("def test_round", "def test_c4_round"))
        with self.assertRaisesRegex(mf.FreezeError, "test_round.*removed or renamed"):
            self.lock([self.ADD, self.SUBTRACT])

    def test_a_mapped_test_that_is_neither_new_by_name_nor_there_before_is_refused(self):
        self.repo.write("tests/test_calc.py", CALC + "\n    def test_add_more(self):\n"
                        "        self.assertEqual(calc.add(1, 1), 2)\n")
        with self.assertRaisesRegex(mf.FreezeError, "test_add_more.*not there at the start"):
            self.lock([self.ADD, dict(self.ADD, name="test_add_more")],
                      **{"tests.test_calc::test_add_more": "passed"})

    def test_a_new_test_next_to_the_existing_ones_is_fine(self):
        self.repo.write("tests/test_calc.py", CALC + "\n    def test_c1_retries(self):\n"
                        "        self.assertEqual(calc.retry(), 3)\n")
        manifest = self.lock([self.ADD, self.SUBTRACT],
                             **{"tests.test_calc::test_c1_retries": "failed"})
        self.assertEqual(manifest["items"]["tests.test_calc::test_c1_retries"], "C1")

    def test_a_test_an_earlier_ticket_named_for_c1_is_not_this_ticket_s_c1(self):
        # The ticket before this one locked its own test_c1_ in the same file.
        earlier = CALC + "\n    def test_c1_divide(self):\n        self.assertEqual(calc.div(6, 3), 2)\n"
        self.repo.write("tests/test_calc.py", earlier)
        self.start = self.repo.commit()
        self.repo.write("tests/test_calc.py", earlier + "\n    def test_c1_retries(self):\n"
                        "        self.assertEqual(calc.retry(), 3)\n")
        manifest = self.lock([self.ADD, self.SUBTRACT],
                             **{"tests.test_calc::test_c1_divide": "passed",
                                "tests.test_calc::test_c1_retries": "failed"})
        self.assertEqual(manifest["items"]["tests.test_calc::test_c1_retries"], "C1")
        self.assertNotIn("tests.test_calc::test_c1_divide", manifest["items"])

    def test_a_file_the_map_names_is_one_of_the_ticket_s_test_files(self):
        # tests/test_divide.py is not under tests: in the ticket, and the test writer
        # cannot change the ticket.
        self.repo.write("tests/test_divide.py", CALC.replace("test_add", "test_c9_divide"))
        self.start = self.repo.commit()
        manifest = self.lock([self.ADD, {"item": "C2", "file": "tests/test_divide.py",
                                         "name": "test_c9_divide"}],
                             **{"tests.test_divide::test_c9_divide": "passed"})
        self.assertEqual(manifest["items"]["tests.test_divide::test_c9_divide"], "C2")
        self.assertIn("tests/test_divide.py", manifest["files"])
        self.assertIn("tests.test_divide::test_c9_divide", manifest["keeps_behavior"])

    def test_the_map_names_no_file_outside_the_project_s_tests(self):
        for path in ("../x.py", "/etc/x.py", ".tollgate/settings.json"):
            with self.subTest(path=path), self.assertRaisesRegex(mf.FreezeError, "outside"):
                self.lock([self.ADD, dict(self.ADD, file=path)])


class PrepareTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        r = self.repo
        r.write(".tollgate/settings.json", settings_text(harness=["ci/**"]))
        r.write("pytest.ini", "[pytest]\n")
        r.write("ci/run.sh", "make test\n")
        r.commit("main")
        r.git("checkout", "-q", "-b", "tg/T-1")
        r.write(mf.ticket_path("T-1"), TICKET)
        r.write("tests/test_t1.py", "# locked\n")
        self.frozen = r.commit("ticket")

    def test_puts_back_harness_and_removes_added_harness(self):
        r = self.repo
        r.write("pytest.ini", "[pytest]\naddopts = -k nothing\n")
        r.write("ci/run.sh", "true\n")
        r.write("src/conftest.py", "collect_ignore = ['tests']\n")
        r.write("src/app.py", "x = 1\n")
        touched = prepare.restore(str(r.path), "main")
        self.assertEqual(sorted(touched), ["ci/run.sh", "pytest.ini", "src/conftest.py"])
        self.assertEqual((r.path / "pytest.ini").read_text(), "[pytest]\n")
        self.assertFalse((r.path / "src/conftest.py").exists())
        self.assertTrue((r.path / "src/app.py").exists())

    def test_keep_harness_leaves_it(self):
        self.repo.write("pytest.ini", "changed\n")
        self.assertEqual(prepare.restore(str(self.repo.path), "main", keep_harness=True), [])

    def test_puts_back_locked_files(self):
        r = self.repo
        r.write("tests/test_t1.py", "# weakened\n")
        m = {"files": {"tests/test_t1.py": "", mf.ticket_path("T-1"): ""}}
        touched = prepare.restore(str(r.path), "main", self.frozen, m)
        self.assertEqual(touched, ["tests/test_t1.py"])
        self.assertEqual((r.path / "tests/test_t1.py").read_text(), "# locked\n")


GO_TICKET = """---
id: T-1
plan: retries
seams: internal/logging.Cause
tests: internal/logging/cause_test.go, internal/components/components_test.go
---
## Current behavior
The cause rule is in internal/components.

## Desired behavior
logging.Cause masks a text and cuts it.

## Checklist
- [C1, must, happy] logging.Cause keeps a short text.
- [C2, must, error] logging.Cause of an invalid text never panics.
- [C3, must, keeps behavior, regression] The components cause is still short: \
internal/components/components_test.go::TestACauseIsShort.

## Not covered
- edge: Cause has no other input.
- boundary: no limit changes.
- integration: Cause reads no file.
- e2e: there is no screen.
- security: Cause reads nothing from a user.
- performance: no time limit is asked for.
- concurrency: Cause keeps no state.

## Out of scope
Other cuts.
"""

COMPONENTS_TEST = """package components

import "testing"

func TestACauseIsShort(t *testing.T) {}

func TestOther(t *testing.T) {}
"""

CAUSE_TEST = """package logging_test

import (
	"testing"

	"example.com/app/internal/logging"
)

func TestC1CauseKeepsAShortText(t *testing.T) { _ = logging.Cause("a", 8) }

func TestC2CauseNeverPanics(t *testing.T) { _ = logging.Cause("\\xff", 8) }
"""

MODULE = "example.com/app/internal/"
# What gotestsum prints when internal/logging does not compile: the build errors, then
# one line per package.
SEAM_OUTPUT = """check-tests..............................................................Failed
=== Errors
# example.com/app/internal/logging_test [example.com/app/internal/logging.test]
internal/logging/cause_test.go:9:59: undefined: logging.Cause
internal/logging/cause_test.go:11:55: undefined: logging.Cause
DONE 2 tests, 1 failure, 1 error in 0.4s
FAIL	example.com/app/internal/logging [build failed]
"""


class GoNotBuiltTest(unittest.TestCase):
    """A new Go test that calls a seam the builder adds does not compile, so gotestsum
    writes one failed TestMain for its package and no case for its tests."""

    MAP: ClassVar[list] = [
        {"item": "C1", "file": "internal/logging/cause_test.go",
         "name": "TestC1CauseKeepsAShortText"},
        {"item": "C2", "file": "internal/logging/cause_test.go", "name": "TestC2CauseNeverPanics"},
        {"item": "C3", "file": "internal/components/components_test.go",
         "name": "TestACauseIsShort"},
    ]

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json", settings_text())
        self.repo.write("go.mod", "module example.com/app\n")
        self.repo.write("internal/components/components_test.go", COMPONENTS_TEST)
        self.start = self.repo.commit("start")
        self.settings = st.load_from_ref(str(self.repo.path), "main")

    def report(self, components="passed", logging="failed"):
        """A gotestsum-shaped report: no file attribute, the import path as class name."""
        failure = "<failure message='Failed'><![CDATA[FAIL]]></failure>"
        main = "" if logging == "empty" else (
            f'    <testcase classname="{MODULE}logging" name="TestMain" time="0.000000">'
            f'{failure if logging == "failed" else ""}</testcase>')
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="1" errors="0" time="0.400000">
  <testsuite tests="2" failures="0" time="0.010000" name="{MODULE}components">
    <properties><property name="go.version" value="go1.25.0 darwin/arm64"></property></properties>
    <testcase classname="{MODULE}components" name="TestACauseIsShort" time="0.000000">\
{"<failure message='Failed'></failure>" if components == "failed" else ""}</testcase>
    <testcase classname="{MODULE}components" name="TestOther" time="0.000000"></testcase>
  </testsuite>
  <testsuite tests="0" failures="0" time="0.000000" name="{MODULE}logging">
    <properties><property name="go.version" value="go1.25.0 darwin/arm64"></property></properties>
{main}
  </testsuite>
</testsuites>
""")
        self.addCleanup(Path(f.name).unlink)
        return {t: {"status": r.status, "file": r.file} for t, r in junit.read(f.name).items()}

    def lock(self, output=SEAM_OUTPUT, cause=CAUSE_TEST, mapped=None, **report):
        import json
        self.repo.write(mf.ticket_path("T-1"), GO_TICKET)
        self.repo.write("internal/logging/cause_test.go", cause)
        self.repo.write(mf.map_path("T-1"), json.dumps(mapped or self.MAP))
        commit = self.repo.commit("test(T-1): the ticket and its locked tests")
        return freeze.record(str(self.repo.path), "T-1", commit, self.start, self.settings,
                             self.report(**report), 1, True, output)["manifest"]

    def test_new_tests_of_a_package_that_needs_a_seam_lock_as_failing(self):
        manifest = self.lock()
        new = [f"{MODULE}logging::TestC1CauseKeepsAShortText",
               f"{MODULE}logging::TestC2CauseNeverPanics"]
        keep = f"{MODULE}components::TestACauseIsShort"
        self.assertEqual(manifest["items"], {new[0]: "C1", new[1]: "C2", keep: "C3"})
        self.assertEqual(manifest["keeps_behavior"], [keep])
        self.assertEqual(manifest["not_built"], new)
        # The gate requires each locked test to run and pass on each try.
        self.assertEqual(sorted(manifest["tests"]), sorted([*new, keep]))
        self.assertNotIn(f"{MODULE}components::TestOther", manifest["tests"])

    def test_an_empty_suite_and_the_build_failed_line_lock_as_failing(self):
        # gotestsum v1.13 writes a package that does not compile as an empty test suite,
        # with no TestMain case; the output names it as FAIL <import path> [build failed].
        manifest = self.lock(logging="empty")
        self.assertEqual(manifest["not_built"], [f"{MODULE}logging::TestC1CauseKeepsAShortText",
                                                 f"{MODULE}logging::TestC2CauseNeverPanics"])
        with self.subTest("no build failed line"), \
                self.assertRaisesRegex(mf.FreezeError, "did not run"):
            self.lock(logging="empty", output=SEAM_OUTPUT.replace(" [build failed]", ""))

    def test_a_keeps_behavior_test_must_still_pass_before_the_build(self):
        with self.assertRaisesRegex(mf.FreezeError, "TestACauseIsShort keeps behavior"):
            self.lock(components="failed")

    def test_a_compile_error_that_is_not_a_seam_is_refused(self):
        other = SEAM_OUTPUT.replace("undefined: logging.Cause", "undefined: strngs.Cut", 1)
        with self.assertRaisesRegex(mf.FreezeError, "TestC1CauseKeepsAShortText.*did not run"):
            self.lock(output=other)
        with self.subTest("no output"), self.assertRaisesRegex(mf.FreezeError, "did not run"):
            self.lock(output="")

    def test_a_package_that_built_is_not_counted_as_failing(self):
        with self.assertRaisesRegex(mf.FreezeError, "TestC1CauseKeepsAShortText.*did not run"):
            self.lock(logging="passed")

    def test_a_mapped_test_the_file_does_not_define_is_refused(self):
        mapped = [*self.MAP, {"item": "C2", "file": "internal/logging/cause_test.go",
                              "name": "TestC2Missing"}]
        with self.assertRaisesRegex(mf.FreezeError, "did not run"):
            self.lock(mapped=mapped)

    def test_a_new_test_named_for_its_item_needs_no_map_entry(self):
        named = CAUSE_TEST.replace("TestC2CauseNeverPanics", "Test_c2_cause_never_panics")
        manifest = self.lock(cause=named, mapped=[self.MAP[0], self.MAP[2]])
        self.assertEqual(manifest["items"][f"{MODULE}logging::Test_c2_cause_never_panics"],
                         "C2")

    def test_a_kept_test_in_the_package_that_does_not_build_is_taken_from_the_start(self):
        # The kept test is in the package of the new tests, so it cannot build before the
        # build. It must pass on the code before the new tests, and after the build.
        old = "package logging\n\nimport \"testing\"\n\nfunc TestACutIsShort(t *testing.T) {\n" \
              "\tt.Log(1)\n}\n"
        self.repo.write("internal/logging/cut_test.go", old)
        self.start = self.repo.commit("an old test in the package")
        mapped = [*self.MAP, {"item": "C3", "file": "internal/logging/cut_test.go",
                              "name": "TestACutIsShort"}]
        keep = f"{MODULE}logging::TestACutIsShort"
        with self.assertRaises(mf.KeptNotRunError):
            self.lock(mapped=mapped)
        at_start = {keep: {"status": "passed", "file": ""}}
        manifest = self.lock_with_start(mapped, at_start)
        self.assertEqual(manifest["kept_at_start"], [keep])
        self.assertEqual(manifest["keeps_behavior"],
                         [f"{MODULE}components::TestACauseIsShort", keep])
        self.assertIn(keep, manifest["tests"])
        with self.subTest("it failed at the start"), \
                self.assertRaisesRegex(mf.FreezeError, "TestACutIsShort keeps behavior"):
            self.lock_with_start(mapped, {keep: {"status": "failed", "file": ""}})
        with self.subTest("it did not run at the start"), \
                self.assertRaisesRegex(mf.FreezeError, "or at the start"):
            self.lock_with_start(mapped, {})
        with self.subTest("its source changed"), \
                self.assertRaisesRegex(mf.FreezeError, "TestACutIsShort was there at the start"):
            self.repo.write("internal/logging/cut_test.go", old.replace("1", "2"))
            self.lock_with_start(mapped, at_start)

    def test_an_edited_go_test_that_was_there_at_the_start_is_refused(self):
        self.repo.write("internal/components/components_test.go", COMPONENTS_TEST.replace(
            "func TestACauseIsShort(t *testing.T) {}", "func TestACauseIsShort(t *testing.T) {\n"
            "\treturn\n}"))
        with self.assertRaisesRegex(mf.FreezeError, "TestACauseIsShort was there at the start, "
                                    "and it changed"):
            self.lock()

    def test_a_go_test_ends_at_the_next_declaration_not_at_a_brace_in_a_string(self):
        raw = ("package components\n\nimport \"testing\"\n\nfunc TestRaw(t *testing.T) {\n"
               "\twant := `\n}\n`\n\t_ = want\n}\n\n// TestNext is new.\nfunc TestNext(t *testing.T) {}\n")
        found = mf.go_test_sources(raw.encode())
        self.assertIn("_ = want", found["TestRaw"])
        self.assertNotIn("TestNext", found["TestRaw"])   # its comment belongs to the next one
        self.assertNotEqual(found["TestRaw"],
                            mf.go_test_sources(raw.replace("_ = want", "return").encode())["TestRaw"])
        # One test on one line: removing the test after it does not change it.
        self.repo.write("internal/components/components_test.go", COMPONENTS_TEST.replace(
            "func TestOther(t *testing.T) {}\n", ""))
        with self.assertRaisesRegex(mf.FreezeError, "TestOther was there at the start, "
                                    "and it was removed"):
            self.lock()

    def test_a_test_file_of_a_language_with_no_parser_must_stay_as_it_was(self):
        self.repo.write("web/app.test.js", "test('adds', () => expect(1 + 1).toBe(2))\n")
        start = self.repo.commit("a js test")
        self.repo.write("web/app.test.js", "test('adds', () => expect(true).toBe(true))\n")
        commit = self.repo.commit("weakened")
        with self.assertRaisesRegex(mf.FreezeError, "web/app.test.js was there at the start, "
                                    "and it changed"):
            mf.check_kept(str(self.repo.path), commit, start, ["web/app.test.js"], [])
        # A new file of such a language is free.
        self.repo.write("web/new.test.js", "test('x', () => {})\n")
        mf.check_kept(str(self.repo.path), self.repo.commit("new"), start, ["web/new.test.js"], [])

    def lock_with_start(self, mapped, at_start):
        import json
        self.repo.write(mf.ticket_path("T-1"), GO_TICKET)
        self.repo.write("internal/logging/cause_test.go", CAUSE_TEST)
        self.repo.write(mf.map_path("T-1"), json.dumps(mapped))
        commit = self.repo.commit("test(T-1): the ticket and its locked tests")
        return freeze.record(str(self.repo.path), "T-1", commit, self.start, self.settings,
                             self.report(), 1, True, SEAM_OUTPUT, at_start)["manifest"]

    def test_a_test_that_was_there_at_the_start_is_not_counted_as_failing(self):
        self.repo.write("internal/logging/cause_test.go", CAUSE_TEST)
        self.start = self.repo.commit("the tests were there")
        with self.assertRaisesRegex(mf.FreezeError, "did not run"):
            self.lock()


class SummaryTest(unittest.TestCase):
    def test_pass_and_fail_text(self):
        self.assertEqual(gate.summary([], 2)[0], "Passed. Tier 2.")
        title, text = gate.summary([{"rule": 3, "file": "a.py", "message": "changed"}], 1)
        self.assertIn("1 finding", title)
        self.assertIn("Rule 3: changed (`a.py`)", text)


if __name__ == "__main__":
    unittest.main()
