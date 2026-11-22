"""Shared helpers for tests: throwaway git repositories and sample files."""

import json
import subprocess
import tempfile
from pathlib import Path

TICKET = """---
id: T-1
plan: retries
seams: POST /deliver
tests: tests/test_t1.py
---
## Current behavior
A failed delivery is dropped.

## Desired behavior
A failed delivery is tried again.

## Checklist
- [C1, must] A delivery that fails twice and then succeeds is marked delivered.
- [C2, must, keeps behavior] A delivery that succeeds at once is sent one time.
- [C3] The wait between tries is written to the log.

## Out of scope
A screen to retry by hand.
"""

JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite name="s">
{cases}
</testsuite></testsuites>
"""


def junit(cases: dict) -> str:
    """cases maps 'classname::name' to passed, failed, or skipped."""
    out = []
    for test_id, status in cases.items():
        cls, name = test_id.split("::")
        inner = {"failed": "<failure/>", "skipped": "<skipped/>"}.get(status, "")
        out.append(f'<testcase classname="{cls}" name="{name}">{inner}</testcase>')
    return JUNIT.format(cases="\n".join(out))


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


class Repo:
    """A git repository in a temporary folder."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        sh(self.path, "git", "init", "-q", "-b", "main")
        sh(self.path, "git", "config", "user.email", "t@example.com")
        sh(self.path, "git", "config", "user.name", "Test")
        sh(self.path, "git", "config", "tag.gpgsign", "false")
        sh(self.path, "git", "config", "commit.gpgsign", "false")

    def write(self, path, text):
        target = self.path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, message="change") -> str:
        sh(self.path, "git", "add", "-A")
        sh(self.path, "git", "commit", "-q", "--allow-empty", "-m", message)
        return sh(self.path, "git", "rev-parse", "HEAD").strip()

    def tag(self, name, message, commit="HEAD"):
        sh(self.path, "git", "tag", "-a", name, "-m", message, commit)

    def git(self, *args):
        return sh(self.path, "git", *args)

    def close(self):
        self._tmp.cleanup()


def settings_text(**extra) -> str:
    base = {"checks": {"tests": {"run": "true", "report": "report.xml"}}, "require_plan": False}
    base.update(extra)
    return json.dumps(base)
