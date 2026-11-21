"""One test for each finding of the independent review of the lock."""

import tempfile
import unittest
from pathlib import Path

from action import freeze, gate, prepare, settings, tiers
from action import manifest as mf
from action.gitio import changed_files
from tests.helpers import TICKET, Repo, settings_text
from tests.test_freeze_prepare import results_file
from tests.test_gate import facts, rules


class NonAsciiPaths(unittest.TestCase):
    def test_a_non_ascii_path_under_github_is_seen(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.commit("base")
        repo.git("checkout", "-q", "-b", "tg/T-1")
        repo.write(".github/workflows/é.yml", "on: push\n")
        repo.write("tests/é/conftest.py", "x = 1\n")
        repo.commit("change")
        found = changed_files(str(repo.path), "main", "HEAD")
        self.assertIn(".github/workflows/é.yml", found)
        self.assertIn("tests/é/conftest.py", found)
        self.assertIn(4, rules(facts(changes=found)))


class FreezeBoundToItsRun(unittest.TestCase):
    def test_a_run_that_froze_another_ticket_fails(self):
        f = facts()
        f.freeze.run["title"] = "tollgate freeze T-2"
        self.assertEqual(rules(f), [1])

    def test_a_manifest_that_differs_from_the_run_record_fails(self):
        f = facts()
        f.freeze.run = dict(f.freeze.run, manifest=dict(f.freeze.manifest, tests=[]))
        self.assertEqual(rules(f), [1])

    def test_a_missing_run_record_fails(self):
        f = facts()
        f.freeze.run["manifest"] = None
        self.assertEqual(rules(f), [1])


class TagNumbers(unittest.TestCase):
    def test_only_plain_ascii_numbers_count(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.commit("base")
        for tail in ("1", "２", "02", "²"):
            repo.tag(f"tg/freeze/T-1/{tail}", '{"ticket": "T-1"}')
        self.assertEqual(gate._freeze(str(repo.path), "T-1").number, 1)

    def test_a_tag_number_that_differs_from_its_manifest_fails(self):
        f = facts()
        f.freeze.manifest["number"] = 2
        self.assertIn(1, rules(f))


class GuardedPathsInTests(unittest.TestCase):
    def test_the_freeze_refuses_harness_in_the_tests_header(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(".tollgate/settings.json", settings_text())
        repo.write(mf.ticket_path("T-1"), TICKET.replace("tests: tests/test_t1.py",
                                                         "tests: tests/test_t1.py, conftest.py"))
        repo.write("tests/test_t1.py", "# tests\n")
        repo.write("conftest.py", "collect_ignore = ['tests']\n")
        commit = repo.commit()
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(
                mf.FreezeError, "conftest.py is harness"):
            freeze.message(str(repo.path), "T-1", commit, results_file(d), "1", "main")

    def test_a_frozen_harness_file_still_counts_for_the_tier(self):
        s = settings.parse('{"tiers": {"4": ["payments/**"]}}')
        self.assertEqual(tiers.tier(s, {"conftest.py": 1}, frozen={"conftest.py"})[0], 4)
        self.assertEqual(tiers.tier(s, {"payments/a.py": 1}, frozen={"payments/a.py"})[0], 4)

    def test_prepare_keeps_the_harness_of_main_over_a_frozen_copy(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(".tollgate/settings.json", settings_text())
        repo.write("pytest.ini", "[pytest]\n")
        repo.commit("main")
        repo.git("checkout", "-q", "-b", "tg/T-1")
        repo.write("pytest.ini", "[pytest]\naddopts = -k nothing\n")
        frozen = repo.commit("frozen harness")
        prepare.restore(str(repo.path), "main", frozen, {"files": {"pytest.ini": ""}})
        self.assertEqual(Path(repo.path, "pytest.ini").read_text(), "[pytest]\n")


class GateCrash(unittest.TestCase):
    def test_a_malformed_results_file_ends_with_2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write('{"unexpected": true}')
            f.flush()
            self.assertEqual(gate.main(["--branch", "tg/T-1", "--results", f.name]), 2)


if __name__ == "__main__":
    unittest.main()
