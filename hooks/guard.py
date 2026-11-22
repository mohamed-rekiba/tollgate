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
- any file at all, for a reviewer, the advisor, or the analyst,
- a file outside the role's own copy, for a role.

It refuses a Bash command that merges into main, uses `--no-verify`, or
changes `core.hooksPath`. A role never pushes. Your own session may push a
branch for review, but never main.

For a role, it also refuses a Read, Grep, or Glob of the key folder, or of the
state folder outside the role's own copy, and a Bash command whose text names
the key folder or the state folder. A command can still hide a path, for
example by building it from parts, so this rule is one layer, not a wall.

A call from one of Tollgate's subagents carries its agent type, such as
"tollgate:builder". The hook applies that role's rules, as if the driver had
named the role. A call from any other subagent gets your own session's rules.
In session mode no driver names the copy, so the hook reads it from the step
file, run/step.json in the state folder, and only when the step is for that
same role. No role can write the state folder, so no role can change it.

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

from gate import state

EDITS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READS = {"Read", "Grep", "Glob"}
GLOB_CHARS = re.compile(r"[*?\[{]")
READ_ONLY = ("reviewer", "advisor", "analyst")   # the one list; policy and roles read it
# What a planner, and your own session, may write under .tollgate/.
DRAFTS = (".tollgate/plans/", ".tollgate/tickets/", ".tollgate/roadmaps/")
MAIN = {"main", "master", "refs/heads/main", "refs/heads/master"}
# The roles a Tollgate subagent can be. The plugin names them "tollgate:<role>".
ROLES = ("analyst", "test_writer", "builder", "reviewer", "advisor", "planner")
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
    if (rel.startswith(".tollgate/") or rel == ".tollgate") and not (
            role in ("planner", "") and rel.startswith(DRAFTS)):
        return f"{rel} is under .tollgate/; only the driver writes there"
    ticket = locked_files(project).get(rel)
    if ticket:
        return f"{rel} is locked by ticket {ticket}; no role may change it"
    return ""


def _places(project: str) -> list:
    """(name, folder) for the two places no role may read: the key folder and the state
    folders of every project."""
    return [("key folder", Path(os.path.realpath(state.key_dir()))),
            ("state folder", Path(os.path.realpath(state.state_dir(project).parent)))]


def check_read(path: str, cwd: str, copy: str, project: str) -> str:
    """For a role: the reason to refuse a read of path, a file or a folder, or ""."""
    target = _real(path or ".", cwd)
    own = Path(os.path.realpath(copy)) if copy else None
    if own is not None and _under(target, own):
        return ""
    for name, folder in _places(project):
        if _under(target, folder):
            return f"{target} is in the {name}, outside the role's own copy"
        if _under(folder, target):
            return f"{target} holds the {name}"
    return ""


def read_target(tool: str, data: dict) -> list:
    """The paths a Read, Grep, or Glob call touches."""
    if tool == "Read":
        return [data.get("file_path") or ""]
    paths = [data.get("path") or "."]
    pattern = str(data.get("pattern") or "")
    if tool == "Glob" and pattern.startswith(("/", "~")):
        # The part of an absolute pattern before its first wildcard is a folder it reads.
        fixed = GLOB_CHARS.split(pattern, 1)[0]
        paths.append(fixed if fixed.endswith("/") or fixed == pattern
                     else os.path.dirname(fixed) or "/")
    return paths


def _forms(folder: Path) -> list:
    """The ways a command may write a folder: its path, and from home with ~ or $HOME."""
    forms = {str(folder)}
    home = Path(os.path.realpath(Path.home()))
    if _under(folder, home) and folder != home:
        rel = folder.relative_to(home).as_posix()
        forms |= {f"~/{rel}", f"$HOME/{rel}", f"${{HOME}}/{rel}"}
    return sorted(forms, key=len, reverse=True)


def check_names(command: str, copy: str, project: str) -> str:
    """For a role: the reason to refuse a command whose text names the key folder or the
    state folder, or "". The role's own copy may be named."""
    text = command
    if copy:
        for own in sorted({copy, os.path.realpath(copy)}, key=len, reverse=True):
            text = text.replace(own, " ")
    for name, folder in _places(project):
        for form in _forms(folder):
            if form in text:
                return f"the command names the {name}, which no role may reach"
    return ""


def step_of(project: str) -> dict:
    """The step that waits for your session, from run/step.json, or {}."""
    try:
        found = json.loads((state.state_dir(project) / "run" / "step.json").read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def _words(part: str) -> list:
    try:
        return shlex.split(part)
    except ValueError:
        return part.split()


def _branch(cwd: str) -> str:
    done = subprocess.run(["git", "-C", cwd or ".", "symbolic-ref", "-q", "--short", "HEAD"],
                          capture_output=True, text=True, check=False)
    return done.stdout.strip()


def _remotes(cwd: str) -> set:
    try:
        out = subprocess.run(["git", "-C", cwd, "remote"], capture_output=True, text=True,
                             check=False, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(out.split())


def is_sync(rest: list, cwd: str) -> bool:
    """True when a merge only brings a remote's main up to date here: --ff-only, and
    every target is a remote's main, such as origin/main or @{u}. A fast-forward
    creates no commit, so it brings in only what the remote already has."""
    if "--ff-only" not in rest:
        return False
    targets = [w for w in rest if not w.startswith("-")]
    if not targets:
        return False
    remotes = _remotes(cwd)
    for target in targets:
        if target in ("@{u}", "@{upstream}") or re.fullmatch(r"(main|master)@\{(u|upstream)\}",
                                                             target):
            continue
        found = re.fullmatch(r"(?:refs/remotes/)?([^/\s]+)/(main|master)", target)
        if not found or found.group(1) not in remotes:
            return False
    return True


def role_of(call: dict, role: str = "") -> str:
    """The role the driver named, or else the role of the Tollgate subagent that
    made the call, or "" for your own session and for any other subagent."""
    if role:
        return role
    name = str(call.get("agent_type") or "").removeprefix("tollgate:")
    return name if name in ROLES else ""


def pushes_main(rest: list, cwd: str) -> bool:
    """rest follows "git push". True when it would update main on the remote."""
    if {"--all", "--mirror"} & set(rest):
        return True
    targets = [w for w in rest if not w.startswith("-")][1:]   # after the remote
    if not targets:
        return _branch(cwd) in MAIN   # git push, or git push <remote>: the current branch
    for target in targets:
        dest = target.lstrip("+").split(":")[-1]
        if (_branch(cwd) if dest == "HEAD" else dest) in MAIN:
            return True
    return False


def check_git(words: list, cwd: str, on_main: bool = False, role: str = "") -> str:
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
    if sub == "push" and role:
        return "no role pushes; the store merges a ready change"
    if sub == "push" and pushes_main(rest, cwd):
        return "the push would change main; main changes only through a reviewed pull request"
    if sub == "config" and any(w.startswith("core.hookspath") for w in lowered):
        return "the command changes core.hooksPath"
    into_main = MAIN & set(rest) or on_main or _branch(cwd) in MAIN
    if sub == "merge" and into_main and not is_sync(rest, cwd):
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


def check_bash(command: str, cwd: str, role: str = "") -> str:
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
                reason = check_git(words[n:], cwd, on_main, role)
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
    named = role
    role = role_of(call, role)
    cwd = call.get("cwd") or os.getcwd()
    project = project or os.environ.get("CLAUDE_PROJECT_DIR") or cwd
    if role and not named and not copy:
        # Session mode: the copy of the step that waits, if the step is for this role.
        step = step_of(project)
        if step.get("role") == role:
            copy = str(step.get("copy") or "")
            if role == "builder" and step.get("policy") == "planner":
                role = "planner"
    if tool in READS and role:
        for path in read_target(tool, data):
            reason = check_read(str(path), cwd, copy, project)
            if reason:
                return reason
        return ""
    if tool in EDITS:
        path = data.get("file_path") or data.get("notebook_path") or ""
        if not path:
            return f"{tool} names no file"
        return check_edit(path, cwd, role, copy, project)
    if tool == "Bash":
        if role in READ_ONLY:
            return f"the {role} reads only; it may not run commands"
        if role:
            reason = check_names(data.get("command", ""), copy, project)
            if reason:
                return reason
        return check_bash(data.get("command", ""), cwd, role)
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
            raise TypeError("not an object")
    except (ValueError, TypeError) as err:
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
