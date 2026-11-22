"""Small helpers that call git."""

import hashlib
import os
import subprocess

# A role can write in its copy, so git there must run none of its code and follow none
# of its object swaps: no hooks, no file system monitor, no replace refs.
SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false"]


def safe_env(env=None) -> dict:
    return {**(env or os.environ), "GIT_NO_REPLACE_OBJECTS": "1"}


class GitError(RuntimeError):
    pass


def git(repo, *args) -> str:
    # The store merges with this too, so the project's own hooks still run here.
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=False, env=safe_env())
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def show_bytes(repo, ref, path) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"],
                          capture_output=True, check=False, env=safe_env())
    return proc.stdout if proc.returncode == 0 else None


def fingerprint(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def changed_files(repo, base, head) -> dict:
    """Return {path: lines added plus removed} between the merge base and head."""
    out = git(repo, "diff", "--numstat", "-z", "--no-renames", f"{base}...{head}")
    files = {}
    # With -z, each entry is "added<TAB>removed<TAB>path<NUL>" and no path is quoted.
    for entry in out.split("\0"):
        if not entry.strip():
            continue
        added, removed, path = entry.lstrip("\n").split("\t", 2)
        files[path] = (0 if added == "-" else int(added)) + (0 if removed == "-" else int(removed))
    return files


def commit_of(repo, ref) -> str | None:
    """The full commit id that ref names, or None when ref names no commit."""
    proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"{ref}^{{commit}}"],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def worktree_of(repo, branch: str) -> str | None:
    """The folder of the worktree that has branch checked out, or None."""
    folder = None
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            folder = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}":
            return folder
    return None
