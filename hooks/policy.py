"""The Claude Code settings file for each role: permission rules, the sandbox, and the hook.

    settings_for(role, copy, project) -> dict
    write(role, copy, project, path) -> path

The roles:

- builder and test_writer read, run commands, and edit only their own copy.
- planner is the builder when it writes a plan. It may also write plans and
  tickets under `.tollgate/` in its copy.
- reviewer, advisor, and analyst read only: no edit, no command.

Every role is denied the key folder, the state folder outside its copy,
`.tollgate/settings.json`, the locked files, and the git commands that push,
merge, skip the checks, or change `core.hooksPath`. The deny rules of Claude Code
match a command by its start only, so the guard hook checks every command again.

UNTESTED with Claude Code itself: `claude -p` has no model access on the
machine where this was built. The tests check the rules that this writes.
"""

import json
import os
import shlex
import sys
from pathlib import Path

from gate import state
from hooks.guard import READ_ONLY

GUARD = Path(__file__).resolve().parent / "guard.py"
ROLES = ("builder", "test_writer", "planner", "reviewer", "advisor", "analyst")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
BASH_DENY = ("git push", "git merge", "git commit --no-verify", "git commit -n",
             "git config core.hooksPath", "git -c core.hooksPath")


def _abs(path: str) -> str:
    """An absolute path in a rule: Claude Code reads //path as absolute. A path that
    is not on this machine, such as /work in a container, stays as it is."""
    return "/" + (os.path.realpath(path) if os.path.exists(path) else os.path.abspath(path))


def _edit(path: str) -> list:
    return [f"{tool}({path})" for tool in EDIT_TOOLS]


def _locked(project: str) -> list:
    if not project:
        return []
    from hooks.guard import locked_files
    return sorted(locked_files(project))


def settings_for(role: str, copy: str, project: str, sandbox: bool = True,
                 hook: bool = True) -> dict:
    """The settings of one role session in its copy. project names the state folder;
    "" leaves out the rules that need it."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    here = _abs(copy)
    deny = []
    keys = _abs(str(state.key_dir()))
    deny += [f"Read({keys}/**)", *_edit(f"{keys}/**")]
    if project:
        mine = state.state_dir(project)
        for kind in state.KINDS:
            if kind != "builders":
                deny += _edit(f"{_abs(str(mine / kind))}/**")
    deny += _edit(f"{here}/.tollgate/settings.json") + _edit(f"{here}/.tollgate/lenses/**")
    if role != "planner":
        deny += _edit(f"{here}/.tollgate/**")
    for path in _locked(project):
        deny += _edit(f"{here}/{path}")
    deny += [f"Bash({c}:*)" for c in BASH_DENY]
    if role in READ_ONLY:
        allow = ["Read", "Grep", "Glob"]
        deny += list(EDIT_TOOLS) + ["Bash", "WebFetch", "WebSearch"]
    else:
        allow = ["Read", "Grep", "Glob", "Bash", *_edit(f"{here}/**")]
    out = {"permissions": {"allow": allow, "deny": deny,
                           "disableBypassPermissionsMode": "disable"}}
    if sandbox:
        # Commands run in Claude Code's sandbox: they write only in the copy.
        out["sandbox"] = {"enabled": True, "autoAllowBashIfSandboxed": role not in READ_ONLY,
                          "allowUnsandboxedCommands": False}
    if hook:
        command = shlex.join([sys.executable, str(GUARD), "--role", role, "--copy",
                              os.path.realpath(copy), "--project",
                              os.path.realpath(project) if project else ""])
        out["hooks"] = {"PreToolUse": [{"matcher": "|".join([*EDIT_TOOLS, "Bash"]),
                                        "hooks": [{"type": "command", "command": command}]}]}
    return out


def write(role: str, copy: str, project: str, path: str) -> str:
    """Write the role's settings file at path, outside the copy. Return the path."""
    target = Path(path)
    if Path(os.path.realpath(target)).is_relative_to(os.path.realpath(copy)):
        raise ValueError("a role's settings file must not be in its own copy")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings_for(role, copy, project), indent=1, sort_keys=True)
                      + "\n")
    return str(target)
