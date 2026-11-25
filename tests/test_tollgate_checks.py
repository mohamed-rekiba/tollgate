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

    def settings(self, **checks):
        Path(self.root, ".tollgate/settings.json").write_text(json.dumps({"checks": checks}))

    def test_a_push_also_runs_each_check_of_the_project_but_not_the_writing_check(self):
        self.settings(tests={"run": "pytest -q"}, style={"run": "ruff check ."},
                      writing={"run": "uv run python .tollgate/checks/check_writing.py"})
        names = [name for name, _ in tc.commands("pre-push", root=str(self.root))]
        self.assertEqual(names, ["push", "check: style", "check: tests"])
        argvs = dict(tc.commands("pre-push", root=str(self.root)))
        self.assertEqual(argvs["check: tests"], ["sh", "-c", "pytest -q"])

    def test_no_other_stage_runs_the_checks_of_the_project(self):
        self.settings(tests={"run": "pytest -q"})
        for stage in ("pre-commit", "commit-msg", "pre-merge-commit"):
            with self.subTest(stage=stage):
                names = [n for n, _ in tc.commands(stage, root=str(self.root))]
                self.assertFalse(any(n.startswith("check: ") for n in names), names)

    def test_a_missing_or_bad_settings_file_adds_no_project_check(self):
        self.assertEqual(tc.project_checks(str(self.root)), [])
        Path(self.root, ".tollgate/settings.json").write_text("not json")
        self.assertEqual(tc.project_checks(str(self.root)), [])
        self.settings(odd="text", empty={"run": ""})
        self.assertEqual(tc.project_checks(str(self.root)), [])

    def test_the_project_checks_run_side_by_side_with_the_push_check(self):
        self.settings(a={"run": "sleep 1"}, b={"run": "sleep 1"})
        self.script("push.py", "time.sleep(1)")
        start = time.monotonic()
        with mock.patch.object(tc, "HERE", self.scripts), \
                mock.patch.object(tc, "STAGES", {"pre-push": [("push", ["push.py"])]}), \
                redirect_stdout(io.StringIO()) as out:
            code = tc.main(["pre-push"], root=str(self.root))
        self.assertEqual(code, 0, out.getvalue())
        self.assertLess(time.monotonic() - start, 2.0)
        for name in ("push", "check: a", "check: b"):
            self.assertIn(f"PASS {name}", out.getvalue())

    def test_a_failing_project_check_fails_the_push_and_shows_its_output(self):
        self.settings(tests={"run": "echo 3 tests failed; exit 1"})
        self.script("push.py", "print('merge ok')")
        with mock.patch.object(tc, "HERE", self.scripts), \
                mock.patch.object(tc, "STAGES", {"pre-push": [("push", ["push.py"])]}), \
                redirect_stdout(io.StringIO()) as out:
            code = tc.main(["pre-push"], root=str(self.root))
        self.assertEqual(code, 1)
        self.assertIn("3 tests failed", out.getvalue())
        self.assertIn("FAIL check: tests", out.getvalue())
        self.assertIn("PASS push", out.getvalue())

    def test_a_project_check_does_not_get_the_variables_of_the_hook(self):
        self.settings(env={"run": "echo remote=${PRE_COMMIT_REMOTE_NAME:-none} "
                                  "dir=${GIT_DIR:-none} head=${GITHEAD_1:-none}"})
        self.script("push.py", "import os; print('push sees', os.environ.get("
                               "'PRE_COMMIT_REMOTE_NAME', 'none'))")
        stages = {"pre-push": [("push", ["push.py"])]}
        hook = {"PRE_COMMIT_REMOTE_NAME": "origin", "GIT_DIR": "/x/.git", "GITHEAD_1": "topic"}
        with mock.patch.dict("os.environ", hook):
            code, out = self.run_stage(stages, ["pre-push"])
        self.assertEqual(code, 0, out)
        self.assertIn("remote=none dir=none head=none", out)
        self.assertIn("push sees origin", out)   # Tollgate's own check keeps what it needs

    def test_project_env_drops_only_the_hook_variables(self):
        env = tc.project_env({"PATH": "/bin", "HOME": "/h", "PRE_COMMIT_HOME": "/cache",
                              "PRE_COMMIT_REMOTE_NAME": "origin", "GIT_DIR": "/x",
                              "GITHEAD_abc": "t", "GIT_AUTHOR_NAME": "a"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h", "PRE_COMMIT_HOME": "/cache",
                               "GIT_AUTHOR_NAME": "a"})

    def test_only_the_commit_message_stage_passes_files_on(self):
        self.assertNotIn("x.py", dict(tc.commands("pre-commit", ["x.py"]))["locked"])
        self.assertIn("msg", dict(tc.commands("commit-msg", ["msg"]))["commit message"])


if __name__ == "__main__":
    unittest.main()
