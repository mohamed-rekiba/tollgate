"""Small helpers that call git."""

import hashlib
import subprocess


class GitError(RuntimeError):
    pass


def git(repo, *args) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def show_bytes(repo, ref, path) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, check=False)
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
