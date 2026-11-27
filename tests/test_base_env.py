"""Tests of setup/base_env.py: the copy of a temp repo is made, checked, removed, and gone."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from driver import roles

ROOT = Path(__file__).resolve().parent.parent


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=False).stdout.strip()


class BaseEnvTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Old values of the two variables: the script must put them back.
        self.old_state = str(Path(tmp.name) / "old-state")
        self.old_keys = str(Path(tmp.name) / "old-keys")
        Path(self.old_state).mkdir()
        Path(self.old_keys).mkdir()
        patch = mock.patch.dict(os.environ, {"TOLLGATE_STATE": self.old_state,
                                             "TOLLGATE_KEYS": self.old_keys})
        patch.start()
        self.addCleanup(patch.stop)
        self.calls = []

    def watch(self):
        """Wrappers that call the real functions and record what they saw."""
        real_make, real_remove = roles.make_copy, roles.remove_copy

        def make(project, name):
            path = real_make(project, name)
            self.calls.append(("make", project, name, path,
                               os.environ.get("TOLLGATE_STATE"), os.environ.get("TOLLGATE_KEYS"),
                               git(path, "remote"), git(path, "rev-parse", "HEAD"),
                               git(project, "rev-parse", "HEAD")))
            return path

        def remove(project, name):
            self.calls.append(("remove", project, name))
            return real_remove(project, name)

        return (mock.patch.object(roles, "make_copy", side_effect=make),
                mock.patch.object(roles, "remove_copy", side_effect=remove))

    def run_main(self, make_patch=None, remove_patch=None) -> tuple:
        mk, rm = self.watch()
        err = io.StringIO()
        with (make_patch or mk), (remove_patch or rm), redirect_stderr(err):
            from setup import base_env
            code = base_env.main()
        return code, err.getvalue()

    def test_c1_main_returns_zero(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)

    def test_c2_make_copy_raises(self):
        boom = mock.patch.object(roles, "make_copy", side_effect=RuntimeError("no clone"))
        code, err = self.run_main(make_patch=boom)
        self.assertNotEqual(code, 0)
        self.assertTrue(err.strip())
        self.assertIn("make", err.lower())

    def test_c2_path_stays_after_remove(self):
        keep = mock.patch.object(roles, "remove_copy", return_value=None)
        mk, _ = self.watch()
        code, err = self.run_main(make_patch=mk, remove_patch=keep)
        self.assertNotEqual(code, 0)
        self.assertTrue(err.strip())
        self.assertIn("remov", err.lower())

    def test_c3_real_functions_called_once_each(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertEqual([c[0] for c in self.calls], ["make", "remove"])
        self.assertEqual(self.calls[0][1:3], self.calls[1][1:3])

    def test_c4_runs_from_another_cwd(self):
        with tempfile.TemporaryDirectory() as other:
            proc = subprocess.run([sys.executable, str(ROOT / "setup" / "base_env.py")],
                                  cwd=other, capture_output=True, text=True, check=False,
                                  timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_c5_temp_folders_removed_and_real_state_untouched(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        make = self.calls[0]
        self.assertNotEqual(make[4], self.old_state)
        self.assertFalse(Path(make[4]).exists())
        self.assertFalse(Path(make[1]).exists())
        self.assertEqual(list(Path(self.old_state).iterdir()), [])

    def test_c5_temp_folders_removed_after_failure(self):
        keep = mock.patch.object(roles, "remove_copy", return_value=None)
        mk, _ = self.watch()
        code, _ = self.run_main(make_patch=mk, remove_patch=keep)
        self.assertNotEqual(code, 0)
        make = self.calls[0]
        self.assertFalse(Path(make[4]).exists())
        self.assertFalse(Path(make[1]).exists())
        self.assertEqual(list(Path(self.old_state).iterdir()), [])

    def test_c6_copy_has_no_origin_and_holds_the_commit(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        make = self.calls[0]
        self.assertNotIn("origin", make[6].split())
        self.assertRegex(make[7], r"^[0-9a-f]{40}$")
        self.assertEqual(make[7], make[8])

    def test_c7_env_set_during_run_and_restored(self):
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        make = self.calls[0]
        self.assertNotEqual(make[4], self.old_state)
        self.assertNotEqual(make[5], self.old_keys)
        self.assertEqual(os.environ["TOLLGATE_STATE"], self.old_state)
        self.assertEqual(os.environ["TOLLGATE_KEYS"], self.old_keys)

    def test_c7_env_restored_after_failure_and_when_unset(self):
        boom = mock.patch.object(roles, "make_copy", side_effect=RuntimeError("no clone"))
        code, _ = self.run_main(make_patch=boom)
        self.assertNotEqual(code, 0)
        self.assertEqual(os.environ["TOLLGATE_STATE"], self.old_state)
        del os.environ["TOLLGATE_STATE"]
        del os.environ["TOLLGATE_KEYS"]
        code, err = self.run_main()
        self.assertEqual(code, 0, err)
        self.assertNotIn("TOLLGATE_STATE", os.environ)
        self.assertNotIn("TOLLGATE_KEYS", os.environ)


if __name__ == "__main__":
    unittest.main()
