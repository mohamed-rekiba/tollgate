"""Tests for the role runner, the isolation, and the builder's copy."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import state
from driver import roles
from tests.driver_fakes import FAKE_ROLE


class StateEnv(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        patch = mock.patch.dict(os.environ, {"TOLLGATE_STATE": str(self.root / "state"),
                                             "TOLLGATE_KEYS": str(self.root / "keys")})
        patch.start()
        self.addCleanup(patch.stop)
        self.project = self.root / "project"
        self.project.mkdir()
        self.copy = state.path(str(self.project), "builders", "T-1")
        self.copy.mkdir()


class AnswerTest(unittest.TestCase):
    def test_reads_the_last_json_block(self):
        text = 'x\n```json\n{"a": 1}\n```\nthen\n```json\n{"a": 2}\n```\n'
        self.assertEqual(roles.last_block(text), {"a": 2})
        with self.assertRaises(roles.RoleError):
            roles.last_block("no block")

    def test_runs_a_fake_role_and_reads_the_cost(self):
        with tempfile.TemporaryDirectory() as d:
            answer = roles.run(f"{sys.executable} {FAKE_ROLE} ok cost=0.25", "advisor",
                               {"reason": "x"}, d, 1)
        self.assertEqual(answer.data["decision"], "park")
        self.assertEqual(answer.cost_usd, 0.25)

    def test_a_failing_role_shows_what_it_printed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(roles.RoleError, "credit balance is too low"):
                roles.run(f"{sys.executable} -c 'print(\"credit balance is too low\"); exit(1)'",
                          "reviewer", {}, d, 1)

    def test_a_role_past_its_time_is_a_timeout(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(roles.RoleTimeout):
            roles.run(f"{sys.executable} -c 'import time; time.sleep(5)'", "builder", {}, d, 0.01)


class SandboxTest(StateEnv):
    """UNTESTED with Claude Code: these check the command line only."""

    def test_claude_gets_its_flags_and_the_role_settings_file(self):
        args = roles.command_line("claude -p", "reviewer", "sandbox", workdir=str(self.copy),
                                  settings_file="/s.json")
        self.assertEqual(args[-6:], ["--output-format", "json", "--allowedTools",
                                     "Read,Grep,Glob", "--settings", "/s.json"])

    def test_a_fake_role_gets_no_flags(self):
        self.assertEqual(roles.command_line("python3 fake.py x", "builder", "sandbox",
                                            settings_file="/s.json"), ["python3", "fake.py", "x"])

    def test_the_settings_file_is_in_the_state_folder_outside_the_copy(self):
        path = roles._settings_file("builder", str(self.copy), str(self.project), "/tmp")
        self.assertTrue(Path(path).is_relative_to(state.state_dir(str(self.project)) / "run"))
        self.assertTrue(json.loads(Path(path).read_text())["sandbox"]["enabled"])


class ContainerTest(StateEnv):
    def args(self, role="builder", workdir=None):
        return roles.command_line("claude -p", role, "container", "img:1",
                                  str(workdir or self.copy))

    def test_the_builder_mounts_its_copy_and_nothing_else(self):
        args = self.args()
        self.assertEqual(args[:3], ["docker", "run", "--rm"])
        mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
        self.assertEqual(mounts, [f"{self.copy}:/work"])
        docker = " ".join(args[:args.index("img:1")])
        self.assertNotIn(os.environ["TOLLGATE_KEYS"], docker)
        self.assertNotIn(".ssh", docker)

    def test_a_reviewer_and_the_advisor_mount_it_read_only(self):
        for role in ("reviewer", "advisor"):
            mounts = [a for a in self.args(role) if a.endswith(":/work:ro")]
            self.assertEqual(mounts, [f"{self.copy}:/work:ro"])
        self.assertFalse([a for a in self.args("builder") if a.endswith(":ro")])

    def test_the_key_folder_is_never_mounted(self):
        keys = Path(os.environ["TOLLGATE_KEYS"])
        keys.mkdir()
        with self.assertRaisesRegex(roles.RoleError, "key folder"):
            self.args(workdir=keys)
        with self.assertRaisesRegex(roles.RoleError, "key folder"):
            self.args(workdir=self.root)

    def test_the_state_folder_is_never_mounted_except_a_copy(self):
        with self.assertRaisesRegex(roles.RoleError, "state folder"):
            self.args(workdir=state.state_dir(str(self.project)))
        with self.assertRaisesRegex(roles.RoleError, "not a builder's copy"):
            self.args(workdir=state.path(str(self.project), "locks"))

    def test_the_container_gets_whichever_model_access_is_set(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "t",
                                          "ANTHROPIC_API_KEY": ""}):
            args = self.args()
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", args)
            self.assertNotIn("ANTHROPIC_API_KEY", args)
            roles.drop_empty_access()
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

    def test_no_image_is_an_error(self):
        with self.assertRaises(roles.RoleError):
            roles.command_line("claude -p", "builder", "container", "", str(self.copy))


class CopyTest(StateEnv):
    def test_the_copy_is_in_the_state_folder_with_no_remote(self):
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.project)], check=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=t", "-c",
                        "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        path = roles.make_copy(str(self.project), "T-2")
        self.assertTrue(Path(path).is_relative_to(state.state_dir(str(self.project)) / "builders"))
        remotes = subprocess.run(["git", "-C", path, "remote"], capture_output=True, text=True,
                                 check=True).stdout
        self.assertEqual(remotes, "")
        self.assertFalse(Path(self.project, ".tollgate").exists())
        roles.remove_copy(str(self.project), "T-2")
        self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
