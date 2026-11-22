"""Refuse a commit that changes a locked file. Python 3, standard library only.

Tollgate copies this file into a project as .tollgate/checks/check_locked.py.
pre-commit runs it before each commit and each merge:

    python3 .tollgate/checks/check_locked.py

A locked file is one of these:

- a file in the manifest of any lock in the state folder: locks/*.json and plans/*.json;
- a file under .tollgate/: the settings, the plans, the tickets, the checks;
- .pre-commit-config.yaml, which runs these checks.

A merge may change them when the commit it merges passed the gate, or is on
main. Every other commit may not. It reads the locks without checking their
signatures: a forged lock can only lock more files.

It needs check_merge.py in the same folder. It ends with 0 when the commit may
go on, and 1 with one line for each locked file it changes.
"""

import importlib.util
import json
import sys
from pathlib import Path

PROTECTED_DIRS = (".tollgate/",)
PROTECTED_FILES = (".pre-commit-config.yaml",)


def _sibling(name):
    sys.dont_write_bytecode = True  # a cache file in .tollgate/checks/ would be a change
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cm = _sibling("check_merge")


def locked_files(project: str) -> set:
    """Every path in a lock manifest or a plan lock of the project."""
    folder = cm.state_dir(project)
    out = set()
    for path in sorted(folder.glob("locks/*.json")) + sorted(folder.glob("plans/*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        out.update((record.get("manifest") or {}).get("files", {}))
        out.update(record.get("files", {}))
    return out


def staged(root) -> list:
    code, out = cm.git(root, "diff", "--cached", "--name-only", "--no-renames", "-z")
    return [p for p in out.split("\0") if p] if code == 0 else []


def merge_allowed(root) -> bool:
    """True when a merge is in progress and each commit it merges passed, or is on main."""
    heads = cm.merge_heads(root)
    return bool(heads) and all(
        cm.git(root, "merge-base", "--is-ancestor", head, f"refs/heads/{cm.MAIN}")[0] == 0
        or not cm.check_commit(root, head) for head in heads)


def check(root) -> list:
    locked = locked_files(cm.project_root(root))
    found = []
    for name in staged(root):
        if name in locked:
            found.append(f"{name} is locked: its tests are frozen. Change the code, not the tests.")
        elif name.startswith(PROTECTED_DIRS) or name in PROTECTED_FILES:
            found.append(f"{name} is Tollgate's file. Only a merge by /tollgate:merge changes it.")
    if found and merge_allowed(root):
        return []
    return found


def main() -> int:
    root = cm.git(".", "rev-parse", "--show-toplevel")[1] or "."
    found = check(root)
    for line in found:
        print(f"check_locked: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
