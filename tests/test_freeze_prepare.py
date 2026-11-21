"""Tests for the freeze command, the restore step, and the workflow templates."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from action import freeze, gate, prepare
from action import manifest as mf
from action.checks import CheckResult, Results
from tests.helpers import TICKET, Repo, settings_text

ROOT = Path(__file__).resolve().parent.parent


def results_file(folder, **status):
    tests = {"test_c1_retries": "failed", "test_c2_sent_once": "passed",
             "test_c3_wait_logged": "failed"}
    tests.update(status)
    r = Results([CheckResult("tests", False)],
                {f"tests.test_t1::{n}": {"status": s, "file": ""} for n, s in tests.items()})
    path = Path(folder, "results.json")
    path.write_text(r.to_json())
    return str(path)


class FreezeTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json", settings_text())
        self.repo.write(mf.ticket_path("T-1"), TICKET)
        self.repo.write("tests/test_t1.py", "# tests\n")
        self.commit = self.repo.commit()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_first_freeze(self):
        name, text = freeze.message(str(self.repo.path), "T-1", self.commit,
                                    results_file(self.tmp.name), "123", "main")
        self.assertEqual(name, "tg/freeze/T-1/1")
        m = mf.loads(text)
        self.assertEqual((m["run_id"], m["number"], m["commit"]), (123, 1, self.commit))

    def test_second_freeze_gets_the_next_number_and_a_third_is_refused(self):
        self.repo.tag("tg/freeze/T-1/1", "x", self.commit)
        name, _ = freeze.message(str(self.repo.path), "T-1", self.commit,
                                 results_file(self.tmp.name), "1", "main")
        self.assertEqual(name, "tg/freeze/T-1/2")
        self.repo.tag("tg/freeze/T-1/2", "x", self.commit)
        with self.assertRaisesRegex(mf.FreezeError, "already has 2 freezes"):
            freeze.message(str(self.repo.path), "T-1", self.commit,
                           results_file(self.tmp.name), "1", "main")

    def test_refuses_a_bad_ticket_id(self):
        with self.assertRaisesRegex(mf.FreezeError, "not a valid ticket id"):
            freeze.message(str(self.repo.path), "T-1;rm", self.commit,
                           results_file(self.tmp.name), "1", "main")

    def test_command_line_writes_name_and_message(self):
        out, name_out = Path(self.tmp.name, "msg"), Path(self.tmp.name, "name")
        code = freeze.main(["--repo", str(self.repo.path), "--ticket", "T-1",
                            "--commit", self.commit, "--results", results_file(self.tmp.name),
                            "--run-id", "9", "--base", "main", "--out", str(out), "--name-out", str(name_out)])
        self.assertEqual(code, 0)
        self.assertEqual(name_out.read_text(), "tg/freeze/T-1/1")
        self.assertEqual(freeze.main(["--repo", str(self.repo.path), "--ticket", "T-1",
                                      "--commit", self.commit, "--results",
                                      results_file(self.tmp.name, test_c1_retries="passed"),
                                      "--run-id", "9", "--base", "main", "--out", str(out),
                                      "--name-out", str(name_out)]), 1)


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


class WorkflowTemplatesTest(unittest.TestCase):
    FILE = ROOT / "workflows/tollgate.yml"

    def jobs(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("no YAML parser here")
        return yaml.safe_load(self.FILE.read_text())["jobs"]

    def test_this_repository_runs_the_template_as_it_is(self):
        # Tollgate guards itself with this file, so the installed copy must match.
        # It compares the copy the commit holds. On GitHub, the test job puts main's
        # harness back on disk before the tests run, so for a change to the workflow
        # the file on disk is main's copy, not the one this commit installs.
        path = ".github/workflows/tollgate.yml"
        proc = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{path}"],
                              capture_output=True, text=True, check=False)
        installed = proc.stdout if proc.returncode == 0 else (
            (ROOT / path).read_text() if (ROOT / path).exists() else None)
        if installed is not None:
            self.assertEqual(installed, self.FILE.read_text(),
                             "run: python3 -m setup.write_workflows --version self")

    def test_no_broad_permissions_and_no_pin_in_the_file(self):
        text = self.FILE.read_text()
        self.assertIn("permissions: {}", text)
        self.assertNotIn("tollgate/action@", text)
        self.assertIn(".tollgate/settings.json", text)

    def test_untrusted_text_never_lands_in_a_shell_line(self):
        bad = re.compile(r"\$\{\{\s*(github\.event\.(pull_request\.head|comment|issue\.title|"
                         r"issue\.body)|inputs\.id|needs\.find\.outputs\.(branch|ticket))")
        block = None
        for line in self.FILE.read_text().splitlines():
            if re.match(r"\s*run:", line):
                block = len(line) - len(line.lstrip())
                self.assertIsNone(bad.search(line), line)
            elif block is not None and line.strip() and len(line) - len(line.lstrip()) <= block:
                block = None
            elif block is not None:
                self.assertIsNone(bad.search(line), line)

    def test_jobs_that_run_the_change_cannot_write(self):
        for name in ("freeze-test", "test"):
            job = self.jobs()[name]
            self.assertEqual(job["permissions"], {"contents": "read"}, name)
            text = str(job)
            self.assertNotIn("secrets.", text)
            for step in job["steps"]:
                if "actions/checkout" in step.get("uses", ""):
                    self.assertEqual(step["with"]["persist-credentials"], False, name)

    def test_there_is_no_gate_job_and_a_failed_check_fails_the_test_job(self):
        self.assertNotIn("gate", self.jobs())
        steps = [s.get("name") for s in self.jobs()["test"]["steps"]]
        self.assertEqual(steps[-1], "Fail when a check failed")

    def test_the_change_is_never_where_the_code_runs_from(self):
        for name, job in self.jobs().items():
            for step in job["steps"]:
                if "actions/checkout" in step.get("uses", "") and step["with"].get("path") == "main":
                    self.assertEqual(step["with"]["ref"], "main", name)


if __name__ == "__main__":
    unittest.main()
