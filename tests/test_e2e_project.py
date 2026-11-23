"""tests/e2e/make_project.py makes a project that a real run can start on. No model runs."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.e2e import make_project


def installed(tool):
    return f"/usr/bin/{tool}"


class MakeProjectTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name, "run")
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)

    def test_the_project_is_set_up_and_next_names_the_analyst_first(self):
        from driver import step
        from gate import sign, state
        paths = make_project.make(self.root, which=installed, install=False)
        project = str(paths["project"])
        self.assertEqual(os.environ["TOLLGATE_STATE"], str(self.root / "state"))
        self.assertTrue(sign.machine_key().is_relative_to(self.root / "keys"))
        self.assertTrue(state.state_dir(project).is_relative_to(self.root / "state"))
        settings = json.loads(subprocess.run(
            ["git", "show", "main:.tollgate/settings.json"], cwd=project, check=True,
            capture_output=True, text=True).stdout)
        self.assertIn("pytest", settings["checks"]["tests"]["run"])
        owner = paths["owner_key"].read_text().split()[:2]
        self.assertEqual([k.split()[:2] for k in settings["owners"]], [owner])
        self.assertEqual(len(settings["signers"]), 1)
        out, code = step.next_step(project, make_project.TASK)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["agent"], "tollgate:analyst")
        self.assertTrue(Path(out["cwd"]).is_relative_to(self.root / "state"))
        printed = make_project.commands(paths)
        self.assertIn(f"driver.step next --project . --task {make_project.TASK}", printed)
        self.assertIn(f"TOLLGATE_KEYS={self.root / 'keys'}", printed)

    def test_a_folder_that_is_not_empty_is_refused(self):
        self.root.mkdir()
        (self.root / "something").write_text("x")
        with self.assertRaises(SystemExit):
            make_project.make(self.root, which=installed, install=False)


if __name__ == "__main__":
    unittest.main()
