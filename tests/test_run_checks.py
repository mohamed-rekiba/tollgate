"""run_checks.py: the project's checks before a push, side by side."""

import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from setup import run_checks


class RunChecksTest(unittest.TestCase):
    def project(self, checks: dict, **settings) -> str:
        root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, root, True)
        Path(root, ".tollgate").mkdir()
        Path(root, ".tollgate/settings.json").write_text(json.dumps({"checks": checks,
                                                                     **settings}))
        return root

    def run_main(self, root: str) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run_checks.main(root)
        return code, out.getvalue()

    def test_two_checks_run_side_by_side(self):
        root = self.project({"a": {"run": "sleep 1"}, "b": {"run": "sleep 1"}})
        start = time.monotonic()
        code, out = self.run_main(root)
        took = time.monotonic() - start
        self.assertEqual(code, 0, out)
        self.assertLess(took, 1.8)   # one after another takes 2 seconds or more
        self.assertIn("PASS a", out)
        self.assertIn("PASS b", out)

    def test_a_failing_check_fails_and_its_output_is_shown(self):
        root = self.project({"good": {"run": "echo fine"},
                             "bad": {"run": "echo the lint found 3 problems; exit 2"}})
        code, out = self.run_main(root)
        self.assertEqual(code, 1)
        self.assertIn("the lint found 3 problems", out)
        self.assertIn("FAIL bad", out)
        self.assertIn("exit code 2", out)
        self.assertIn("PASS good", out)
        self.assertIn("run_checks: failed: bad", out)

    def test_a_check_that_runs_out_of_time_fails(self):
        root = self.project({"slow": {"run": "sleep 30", "minutes": 0.02}})
        start = time.monotonic()
        code, out = self.run_main(root)
        self.assertEqual(code, 1)
        self.assertLess(time.monotonic() - start, 10)
        self.assertIn("FAIL slow", out)
        self.assertIn("ran out of time after 0.02 minutes", out)

    def test_check_minutes_is_the_time_limit_of_a_check_with_none(self):
        root = self.project({"slow": {"run": "sleep 30"}}, check_minutes=0.02)
        code, out = self.run_main(root)
        self.assertEqual(code, 1)
        self.assertIn("ran out of time", out)

    def test_parallel_false_runs_one_at_a_time_in_name_order(self):
        root = self.project({"b": {"run": "echo second"}, "a": {"run": "sleep 0.3; echo first"}},
                            parallel=False)
        code, out = self.run_main(root)
        self.assertEqual(code, 0, out)
        self.assertLess(out.index("PASS a"), out.index("PASS b"))
        self.assertLess(out.index("first"), out.index("second"))

    def test_a_number_limits_how_many_run_at_once(self):
        settings = {"parallel": 2}
        self.assertEqual(run_checks.jobs(settings, 5), 2)
        self.assertEqual(run_checks.jobs({"parallel": True}, 5), 5)
        self.assertEqual(run_checks.jobs({}, 3), 3)
        self.assertEqual(run_checks.jobs({"parallel": False}, 5), 1)
        self.assertEqual(run_checks.jobs({"parallel": 9}, 2), 2)

    def test_the_writing_check_is_left_to_its_own_hook(self):
        names = [n for n, _, _ in run_checks.checks({"checks": {
            "writing": {"run": "x"}, "words": {"run": "python3 .tollgate/checks/check_writing.py"},
            "tests": {"run": "y"}}})]
        self.assertEqual(names, ["tests"])

    def test_no_settings_file_runs_nothing(self):
        root = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, root, True)
        code, out = self.run_main(root)
        self.assertEqual(code, 0)
        self.assertIn("no check runs", out)


if __name__ == "__main__":
    unittest.main()
