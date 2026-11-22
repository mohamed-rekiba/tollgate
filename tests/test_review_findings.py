"""One test for each finding of the independent review of the lock."""

import tempfile
import unittest
from pathlib import Path

from gate import freeze, prepare, settings, tiers
from gate import manifest as mf
from gate.gitio import changed_files
from tests.helpers import TICKET, Repo, settings_text
from tests.test_freeze_prepare import results_file, results_of


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
        self.assertEqual(tiers.tier(settings.parse("{}"), found)[0], 4)


class FreePathsAndRenames(unittest.TestCase):
    def test_moving_code_into_docs_is_not_free(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write("src/x.py", "x = 1\n" * 20)
        repo.commit("base")
        repo.git("checkout", "-q", "-b", "docs/move")
        (repo.path / "docs").mkdir()
        repo.git("mv", "src/x.py", "docs/x.py")
        repo.commit("move")
        found = changed_files(str(repo.path), "main", "HEAD")
        self.assertEqual(sorted(found), ["docs/x.py", "src/x.py"])


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
            freeze.record(str(repo.path), "T-1", commit, commit,
                          settings.load_from_ref(str(repo.path), "main"),
                          results_of(results_file(d)), 1)

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


if __name__ == "__main__":
    unittest.main()
