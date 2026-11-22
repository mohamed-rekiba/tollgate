"""Roles run in a container, on their own copy of the project.

    TOLLGATE_TEST_IMAGE=<image with python3 and git> python3 -m unittest tests.proof_container -v

It skips when there is no image or no container daemon. A model is not needed:
the roles are fake roles with the same contract.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from driver import roles
from tests.driver_fakes import FAKE_ROLE
from tests.proof_common import Project, events, tries

IMAGE = os.environ.get("TOLLGATE_TEST_IMAGE", "")


def daemon_up() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, check=False,
                              timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


PROBE = r'''
import json, os, subprocess, sys
prompt = sys.stdin.read()
open("from_container.txt", "w").write("written inside\n")
push = subprocess.run(["git", "push", "origin", "HEAD:refs/heads/escape"],
                      capture_output=True, text=True)
data = {"push_code": push.returncode, "push_err": push.stderr.strip()[-200:],
        "env": sorted(k for k in os.environ if "TOKEN" in k or "SECRET" in k),
        "home_files": sorted(os.listdir(os.environ.get("HOME", "/tmp"))),
        "uid": os.getuid()}
print(json.dumps({"result": "```json\n" + json.dumps(data) + "\n```", "total_cost_usd": 0.01}))
'''


@unittest.skipUnless(IMAGE and daemon_up(), "needs TOLLGATE_TEST_IMAGE and a container daemon")
class ContainerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = Path(self.tmp.name, "server.git")
        self.copy = Path(self.tmp.name, "copy")
        subprocess.run(["git", "init", "-q", "--bare", str(self.server)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.copy)], check=True)
        subprocess.run(["git", "-C", str(self.copy), "remote", "add", "origin", str(self.server)],
                       check=True)
        subprocess.run(["git", "-C", str(self.copy), "-c", "user.name=t", "-c",
                        "user.email=t@e", "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        Path(self.copy, "probe.py").write_text(PROBE)

    def test_a_role_in_the_container_works_on_the_copy_and_cannot_push(self):
        env_before = dict(os.environ)
        os.environ["DEPLOY_TOKEN"] = "must-not-reach-the-container"
        self.addCleanup(os.environ.clear)
        self.addCleanup(os.environ.update, env_before)
        answer = roles.run("python3 probe.py", "builder", {"x": 1}, str(self.copy), 2,
                           isolation="container", image=IMAGE)
        data = answer.data
        self.assertEqual(Path(self.copy, "from_container.txt").read_text(), "written inside\n")
        self.assertNotEqual(data["push_code"], 0, data)
        self.assertEqual(data["env"], [])
        self.assertEqual(data["home_files"], [])
        self.assertEqual(data["uid"], os.getuid())
        self.assertEqual(answer.cost_usd, 0.01)
        refs = subprocess.run(["git", "-C", str(self.server), "for-each-ref"],
                              capture_output=True, text=True, check=True).stdout
        self.assertNotIn("escape", refs)

    def test_the_driver_builds_a_ticket_with_every_role_in_a_container(self):
        role = "python3 fake_role.py"
        p = Project(isolation="container", container_image=IMAGE,
                    ai={"builder": f"{role} pass2", "reviewer": f"{role} ok",
                        "advisor": ["person"]})
        self.addCleanup(p.close)
        Path(p.project, "fake_role.py").write_text(Path(FAKE_ROLE).read_text())
        subprocess.run(["git", "add", "fake_role.py"], cwd=p.project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fake role"], cwd=p.project, check=True)
        result = p.drive()
        self.assertEqual(result.returncode, 0, result.stderr)
        log = p.log_of("T-1")
        self.assertEqual([e["event"] for e in tries(log)], ["try_failed", "try_passed"])
        self.assertEqual(events(log)[-1], "waiting_for_merge")


if __name__ == "__main__":
    unittest.main()
