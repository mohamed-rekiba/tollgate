"""What the end-to-end proofs share: a sample project on this machine with the real
store, an owner key, and the commands a person runs.

Each driver, task, and roadmap runs as its own process, as the task skill starts
it. Only the AI roles are fake: see fake_role.py. Nothing calls the network.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from driver.log import read
from gate import sign, state
from gate.store import Store
from tests.driver_fakes import FAKE_ROLE, Sample

ROOT = Path(__file__).resolve().parent.parent
ROLE = f"{sys.executable} {FAKE_ROLE}"


class Project(Sample):
    """A sample project whose settings list an owner key, so a person can approve."""

    def __init__(self, ticket=True, **settings_args):
        self.settings_args = settings_args
        super().__init__(ticket=ticket, **settings_args)

    def write_settings(self, **settings_args):
        self.owner = self.root / "owner"
        if not self.owner.exists():
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "owner",
                            "-f", str(self.owner)], check=True)
        settings_args.setdefault("owners", [Path(f"{self.owner}.pub").read_text().strip()])
        super().write_settings(**settings_args)

    @property
    def store(self) -> Store:
        return Store(str(self.project))

    def run(self, module: str, *args, cwd=None, timeout=600) -> subprocess.CompletedProcess:
        """Run python3 -m <module> as its own process, in the project folder or in cwd."""
        return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd or self.project,
                              env={**os.environ, "PYTHONPATH": str(ROOT)}, capture_output=True,
                              text=True,
                              timeout=timeout, check=False)

    def drive(self, ticket="T-1") -> subprocess.CompletedProcess:
        return self.run("driver.driver", "--project", ".", "--ticket", ticket)

    def task(self, task="demo", request="Add shout and whisper.") -> subprocess.CompletedProcess:
        return self.run("driver.task", "--project", ".", "--task", task, "--request", request)

    def log_of(self, name: str) -> list:
        return read(str(state.path(str(self.project), "logs", f"{name}.jsonl")))

    def main_has(self, commit: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", commit, "main"],
                              cwd=self.project, check=False).returncode == 0

    def main_log(self) -> str:
        return subprocess.run(["git", "log", "--format=%s", "main"], cwd=self.project,
                              capture_output=True, text=True, check=True).stdout

    def lock(self, ticket="T-1") -> dict:
        """The ticket's lock, verified with the signers on main."""
        signers = json.loads(subprocess.run(
            ["git", "show", "main:.tollgate/settings.json"], cwd=self.project,
            capture_output=True, text=True, check=True).stdout)["signers"]
        return sign.read(state.path(str(self.project), "locks", f"{ticket}.json"),
                         "tollgate-lock", signers)


def events(log: list) -> list:
    return [e["event"] for e in log]


def tries(log: list) -> list:
    return [e for e in log if e["event"] in ("try_failed", "try_passed")]
