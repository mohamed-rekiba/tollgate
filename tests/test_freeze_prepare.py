"""Tests for the freeze command and the restore step."""

import tempfile
import unittest
from pathlib import Path

from gate import freeze, gate, prepare
from gate import settings as st
from gate import manifest as mf
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
        self.assertEqual(sorted(lock["manifest"]), ["files", "keeps_behavior", "tests"])
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


class SummaryTest(unittest.TestCase):
    def test_pass_and_fail_text(self):
        self.assertEqual(gate.summary([], 2)[0], "Passed. Tier 2.")
        title, text = gate.summary([{"rule": 3, "file": "a.py", "message": "changed"}], 1)
        self.assertIn("1 finding", title)
        self.assertIn("Rule 3: changed (`a.py`)", text)


if __name__ == "__main__":
    unittest.main()
