"""Tests of setup/tollgate_checks.py: the checks of one stage, side by side."""

import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from setup import tollgate_checks as tc


class TollgateChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scripts = self.root / ".tollgate" / "checks"
        self.scripts.mkdir(parents=True)

    def script(self, name: str, body: str) -> None:
        (self.scripts / name).write_text("import sys, time\n" + body + "\n")

    def run_stage(self, stages: dict, argv: list) -> tuple:
        out = io.StringIO()
        with mock.patch.object(tc, "HERE", self.scripts), \
                mock.patch.object(tc, "STAGES", stages), redirect_stdout(out):
            code = tc.main(argv, root=str(self.root))
        return code, out.getvalue()

    def test_each_stage_names_the_checks_of_that_git_step(self):
        names = {stage: [script for _, (script, *_) in checks]
                 for stage, checks in tc.STAGES.items()}
        self.assertEqual(names, {
            "pre-commit": ["check_locked.py", "check_writing.py"],
            "commit-msg": ["check_commit_msg.py"],
            "pre-merge-commit": ["check_locked.py", "check_merge.py"],
            "pre-push": ["check_merge.py"]})
        argvs = dict(tc.commands("pre-commit"))
        self.assertEqual(argvs["writing"][-1], "--staged")
        self.assertEqual(dict(tc.commands("pre-merge-commit"))["merge"][-1], "merge")
        self.assertEqual(dict(tc.commands("pre-push"))["push"][-1], "push")

    def test_a_mistyped_stage_is_refused(self):
        for argv in (["post-commit"], ["pre-pull"]):
            with self.subTest(argv=argv), redirect_stdout(io.StringIO()):
                self.assertEqual(tc.main(argv, root=str(self.root)), 2)

    def test_the_stage_is_worked_out_from_what_pre_commit_and_git_give_the_hook(self):
        message = ".git/COMMIT_EDITMSG"
        cases = [
            ("a push", [], {"PRE_COMMIT_REMOTE_NAME": "origin"}, "pre-push", []),
            ("a push with refs", [], {"PRE_COMMIT_REMOTE_NAME": "origin",
                                      "PRE_COMMIT_TO_REF": "abc"}, "pre-push", []),
            ("a commit message", [message], {}, "commit-msg", [message]),
            ("a merge message", ["/r/.git/MERGE_MSG"], {}, "commit-msg", ["/r/.git/MERGE_MSG"]),
            ("a merge", [], {"GITHEAD_1234": "topic"}, "pre-merge-commit", []),
            ("a commit", [], {}, "pre-commit", []),
            ("a manual run with refs", [], {"PRE_COMMIT_TO_REF": "abc",
                                            "PRE_COMMIT_FROM_REF": "def"}, "pre-commit", []),
        ]
        for label, args, env, stage, files in cases:
            with self.subTest(label):
                self.assertEqual(tc.stage_of(args, env), (stage, files))

    def test_a_push_wins_over_a_message_file_and_a_merge(self):
        env = {"PRE_COMMIT_REMOTE_NAME": "origin", "GITHEAD_1": "x"}
        self.assertEqual(tc.stage_of([".git/COMMIT_EDITMSG"], env)[0], "pre-push")

    def test_a_run_with_no_stage_checks_the_stage_that_git_is_in(self):
        self.script("push.py", "print('push check')")
        self.script("msg.py", "print('message check', sys.argv[1:])")
        stages = {"pre-push": [("push", ["push.py"])], "commit-msg": [("m", ["msg.py"])]}
        with mock.patch.dict("os.environ", {"PRE_COMMIT_REMOTE_NAME": "origin"}):
            code, out = self.run_stage(stages, [])
        self.assertEqual(code, 0, out)
        self.assertIn("PASS push", out)
        self.assertNotIn("PASS m", out)
        message = str(self.root / "COMMIT_EDITMSG")
        with mock.patch.dict("os.environ", {}, clear=False) as env:
            env.pop("PRE_COMMIT_REMOTE_NAME", None)
            code, out = self.run_stage(stages, [message])
        self.assertEqual(code, 0, out)
        self.assertIn("message check", out)
        self.assertNotIn("PASS push", out)

    def test_the_checks_of_a_stage_run_side_by_side(self):
        self.script("a.py", "time.sleep(1)")
        self.script("b.py", "time.sleep(1)")
        start = time.monotonic()
        code, out = self.run_stage({"pre-commit": [("a", ["a.py"]), ("b", ["b.py"])]},
                                   ["pre-commit"])
        took = time.monotonic() - start
        self.assertEqual(code, 0, out)
        self.assertLess(took, 1.8)
        self.assertIn("PASS a", out)
        self.assertIn("PASS b", out)

    def test_parallel_false_runs_one_at_a_time(self):
        Path(self.root, ".tollgate/settings.json").write_text(json.dumps({"parallel": False}))
        self.script("a.py", "time.sleep(0.6)")
        self.script("b.py", "time.sleep(0.6)")
        start = time.monotonic()
        code, _ = self.run_stage({"pre-commit": [("a", ["a.py"]), ("b", ["b.py"])]},
                                 ["pre-commit"])
        self.assertEqual(code, 0)
        self.assertGreaterEqual(time.monotonic() - start, 1.2)

    def test_a_failing_check_fails_the_stage_and_shows_its_output(self):
        self.script("ok.py", "print('fine')")
        self.script("bad.py", "print('word to avoid on line 3'); sys.exit(1)")
        code, out = self.run_stage({"pre-commit": [("ok", ["ok.py"]), ("bad", ["bad.py"])]},
                                   ["pre-commit"])
        self.assertEqual(code, 1)
        self.assertIn("word to avoid on line 3", out)
        self.assertIn("FAIL bad", out)
        self.assertIn("PASS ok", out)

    def test_the_commit_message_file_reaches_the_check(self):
        message = self.root / "COMMIT_EDITMSG"
        message.write_text("fix(x): a subject\n")
        self.script("msg.py", "print('got', open(sys.argv[1]).read().strip()); "
                              "sys.exit(0 if sys.argv[1:] else 1)")
        code, out = self.run_stage({"commit-msg": [("commit message", ["msg.py"])]},
                                   ["commit-msg", str(message)])
        self.assertEqual(code, 0, out)
        self.assertIn("got fix(x): a subject", out)

    def test_no_stage_runs_a_check_of_the_project(self):
        # pre-commit runs the project's checks as hooks of their own.
        Path(self.root, ".tollgate/settings.json").write_text(json.dumps({"checks": {
            "tests": {"hook": "check-tests"}, "style": {"run": "ruff check ."}}}))
        for stage in tc.STAGES:
            with self.subTest(stage=stage):
                names = [n for n, _ in tc.commands(stage)]
                self.assertEqual(names, [n for n, _ in tc.STAGES[stage]])

    def test_a_commit_or_a_merge_that_a_test_makes_during_a_push_is_not_a_push(self):
        # pre-commit runs a project's tests at a push with the name of the remote set. A
        # test that commits in a repository of its own runs Tollgate's hook there, and git
        # gives that hook an index file, which it never gives a push.
        push = {"PRE_COMMIT_REMOTE_NAME": "origin", "PRE_COMMIT_REMOTE_URL": "u"}
        self.assertEqual(tc.stage_of([], {**push, "GIT_INDEX_FILE": ".git/index"}),
                         ("pre-commit", []))
        self.assertEqual(tc.stage_of([], {**push, "GIT_INDEX_FILE": ".git/index",
                                          "GITHEAD_1": "topic"})[0], "pre-merge-commit")
        message = ".git/COMMIT_EDITMSG"
        self.assertEqual(tc.stage_of([message], {**push, "GIT_INDEX_FILE": ".git/index"}),
                         ("commit-msg", [message]))

    def test_only_the_commit_message_stage_passes_files_on(self):
        self.assertNotIn("x.py", dict(tc.commands("pre-commit", ["x.py"]))["locked"])
        self.assertIn("msg", dict(tc.commands("commit-msg", ["msg"]))["commit message"])


if __name__ == "__main__":
    unittest.main()
