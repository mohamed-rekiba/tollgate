"""Base check env_up_down: a copy of a temp repo is made, checked, removed, and gone.

    python3 setup/base_env.py

It runs in temp folders, with TOLLGATE_STATE and TOLLGATE_KEYS set only for the
run. It ends with 0, or prints the failed step to stderr and ends with 1.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from driver import roles

NAME = "env-check"
# What a git call or a copy step can raise.
STEP_ERRORS = (OSError, subprocess.SubprocessError, RuntimeError)


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def run(project: str) -> str | None:
    """Make, check, remove, and check the copy. Return the failed step, or None."""
    try:
        path = roles.make_copy(project, NAME)
    except STEP_ERRORS as exc:
        return f"make copy failed: {exc}"
    if not Path(path).is_dir():
        return f"make copy failed: {path} is not a folder"
    try:
        if git(path, "remote"):
            return "check copy failed: the copy has a remote"
        if git(path, "rev-parse", "HEAD") != git(project, "rev-parse", "HEAD"):
            return "check copy failed: the copy lacks the commit of the repo"
    except STEP_ERRORS as exc:
        return f"check copy failed: {exc}"
    try:
        roles.remove_copy(project, NAME)
    except STEP_ERRORS as exc:
        return f"remove copy failed: {exc}"
    if Path(path).exists():
        return f"remove copy failed: {path} is still there"
    return None


def main() -> int:
    names = ("TOLLGATE_STATE", "TOLLGATE_KEYS")
    old = {n: os.environ.get(n) for n in names}
    tmp = tempfile.mkdtemp(prefix="tollgate-env-")
    try:
        project = str(Path(tmp) / "repo")
        os.environ["TOLLGATE_STATE"] = str(Path(tmp) / "state")
        os.environ["TOLLGATE_KEYS"] = str(Path(tmp) / "keys")
        try:
            Path(project).mkdir()
            git(project, "init", "-q", "-b", "main")
            git(project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                "--allow-empty", "-m", "init")
        except STEP_ERRORS as exc:
            print(f"base env failed: make repo: {exc}", file=sys.stderr)
            return 1
        failed = run(project)
        if failed:
            print(f"base env failed: {failed}", file=sys.stderr)
            return 1
        return 0
    finally:
        for n, v in old.items():
            if v is None:
                os.environ.pop(n, None)
            else:
                os.environ[n] = v
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
