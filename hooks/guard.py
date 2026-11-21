#!/usr/bin/env python3
"""The PreToolUse hook: refuse a tool call that breaks Tollgate's rules.

Claude Code runs it before each tool call and sends the call as JSON on
standard input. Exit 0 lets the call run. Exit 2 refuses it, and Claude Code
shows the reason on standard error to the session.

    python3 hooks/guard.py [--role builder] [--copy <folder>] [--project <folder>]

With no role, it guards your own session in the project.

It refuses an edit (Edit, Write, MultiEdit, NotebookEdit) of:

- a file in the lock of any ticket,
- a file under `.tollgate/` (a planner, or your own session, may write plans,
  tickets, and roadmaps there),
- a file in the state folder, except in the role's own copy,
- a file in the key folder,
- any file at all, for a reviewer or the advisor,
- a file outside the role's own copy, for a role.

It refuses a Bash command that pushes, merges into main, uses
`--no-verify`, or changes `core.hooksPath`.

This hook is one layer. The gate and the signed records hold even when a role
gets past it, for example by writing a file from a Bash command.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gate import state  # noqa: E402

EDITS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_ONLY = {"reviewer", "advisor"}
# What a planner, and your own session, may write under .tollgate/.
DRAFTS = (".tollgate/plans/", ".tollgate/tickets/", ".tollgate/roadmaps/")
MAIN = {"main", "master", "refs/heads/main", "refs/heads/master"}
SPLIT = re.compile(r"\|\||&&|[;&|\n()`]|\$\(")
# Short options of git commit that take a value, so "-m -n" is a message, not --no-verify.
TAKES_VALUE = {"-m", "-F", "-C", "-c", "-t", "--author", "--message", "--file", "--date"}


def _real(path: str, cwd: str) -> Path:
    return Path(os.path.realpath(os.path.join(cwd or ".", os.path.expanduser(path))))


def _under(path: Path, folder: Path) -> bool:
    return path == folder or path.is_relative_to(folder)


def locked_files(project: str) -> dict:
    """{path: ticket} for each file in the lock of any ticket of the project."""
    found = {}
    folder = state.state_dir(project) / "locks"
    for lock in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            record = json.loads(lock.read_text())
            for path in record["manifest"]["files"]:
                found[path] = record.get("ticket", lock.stem)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def check_edit(path: str, cwd: str, role: str, copy: str, project: str) -> str:
    """The reason to refuse an edit of path, or "" to let it run."""
    if role in READ_ONLY:
        return f"the {role} reads only; it may not edit {path}"
    target = _real(path, cwd)
    if _under(target, Path(os.path.realpath(state.key_dir()))):
        return f"{target} is in the key folder"
    own = Path(os.path.realpath(copy)) if copy else None
    in_copy = own is not None and _under(target, own)
    root = Path(os.path.realpath(state.state_dir(project).parent))
    if _under(target, root) and not in_copy:
        return f"{target} is in the state folder, outside the role's own copy"
    if role and not in_copy:
        return f"{target} is outside the role's own copy"
    base = own if in_copy else Path(os.path.realpath(project))
    if not _under(target, base):
        return ""
    rel = target.relative_to(base).as_posix()
    if rel.startswith(".tollgate/") or rel == ".tollgate":
        if not (role in ("planner", "") and rel.startswith(DRAFTS)):
            return f"{rel} is under .tollgate/; only the driver writes there"
    ticket = locked_files(project).get(rel)
    if ticket:
        return f"{rel} is locked by ticket {ticket}; no role may change it"
    return ""


def _words(part: str) -> list:
    try:
        return shlex.split(part)
    except ValueError:
        return part.split()


def _branch(cwd: str) -> str:
    done = subprocess.run(["git", "-C", cwd or ".", "symbolic-ref", "-q", "--short", "HEAD"],
                          capture_output=True, text=True, check=False)
    return done.stdout.strip()


def check_git(words: list, cwd: str, on_main: bool = False) -> str:
    """words start at a git command. on_main is true when an earlier part of the
    command checked out main. The reason to refuse it, or ""."""
    i, configs = 1, []
    while i < len(words) and words[i].startswith("-"):
        if words[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            if words[i] == "-c" and i + 1 < len(words):
                configs.append(words[i + 1])
            i += 2
        else:
            if words[i].startswith("-c") and len(words[i]) > 2:
                configs.append(words[i][2:])
            i += 1
    if any(c.lower().startswith("core.hookspath") for c in configs):
        return "the command changes core.hooksPath"
    sub, rest = (words[i], words[i + 1:]) if i < len(words) else ("", [])
    lowered = [w.lower() for w in rest]
    if sub == "push":
        return "no role pushes; the store merges a ready change"
    if sub == "config" and any(w.startswith("core.hookspath") for w in lowered):
        return "the command changes core.hooksPath"
    if sub == "merge" and (MAIN & set(rest) or on_main or _branch(cwd) in MAIN):
        return "only the store merges into main"
    if sub == "commit":
        for n, w in enumerate(rest):
            if w == "--":
                break
            prev = rest[n - 1] if n else ""
            if prev in TAKES_VALUE:
                continue
            if re.fullmatch(r"-[a-zA-Z]*n[a-zA-Z]*", w):
                return "git commit -n skips the checks before a commit"
    return ""


def check_bash(command: str, cwd: str) -> str:
    """The reason to refuse a Bash command, or ""."""
    if "--no-verify" in command:
        return "--no-verify skips the checks before a commit or a push"
    if re.search(r"core\.hookspath", command, re.IGNORECASE):
        return "the command changes core.hooksPath"
    on_main = False
    for part in SPLIT.split(command):
        words = _words(part)
        for n, word in enumerate(words):
            if Path(word).name == "git":
                reason = check_git(words[n:], cwd, on_main)
                if reason:
                    return reason
                if set(words[n + 1:n + 2]) & {"checkout", "switch"}:
                    on_main = bool(MAIN & set(words[n + 2:]))
                break
    return ""


def decide(call: dict, role: str = "", copy: str = "", project: str = "") -> str:
    """The reason to refuse the tool call, or "" to let it run."""
    tool = call.get("tool_name", "")
    data = call.get("tool_input") or {}
    cwd = call.get("cwd") or os.getcwd()
    project = project or os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    if tool in EDITS:
        path = data.get("file_path") or data.get("notebook_path") or ""
        if not path:
            return f"{tool} names no file"
        return check_edit(path, cwd, role, copy, project)
    if tool == "Bash":
        if role in READ_ONLY:
            return f"the {role} reads only; it may not run commands"
        return check_bash(data.get("command", ""), cwd)
    return ""


def main(argv=None, stdin=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate guard", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--role", default=os.environ.get("TOLLGATE_ROLE", ""))
    parser.add_argument("--copy", default=os.environ.get("TOLLGATE_COPY", ""))
    parser.add_argument("--project", default=os.environ.get("TOLLGATE_PROJECT", ""))
    args = parser.parse_args(argv)
    try:
        call = json.loads((stdin or sys.stdin).read())
        if not isinstance(call, dict):
            raise ValueError("not an object")
    except ValueError as err:
        # A guard that cannot read the call refuses it.
        print(f"tollgate: the hook could not read the tool call: {err}", file=sys.stderr)
        return 2
    reason = decide(call, args.role, args.copy, args.project)
    if reason:
        print(f"tollgate: refused. {reason[:1].upper()}{reason[1:]}.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
