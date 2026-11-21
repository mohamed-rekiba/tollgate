"""The role runner, the builder's copy, and the isolation.

A role is one AI session. The runner sends the role file and the inputs on
standard input and reads one JSON answer. The command comes from the settings.
Claude Code gets its flags. Any other command is a fake role with the same
contract: read the prompt on standard input, print {"result": ..., "total_cost_usd": ...}.

Isolation, from the settings `isolation`:

- "container": the role runs in Docker. Only the role's own copy is mounted,
  read-only for a reviewer and the advisor. The key folder and the rest of the
  state folder are never mounted.
- "sandbox": Claude Code runs with a settings file for the role that turns on
  its sandbox, the permission rules, and the guard hook. UNTESTED: `claude -p`
  has no model access on the machine where this was built.

A fake role runs as a plain process in both modes, except in a container when
the settings name an image.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from gate import state

ROOT = Path(__file__).resolve().parent.parent
ROLES = ROOT / "roles"
LENSES = ROOT / "lenses"
# Claude Code reads one of these. An API key comes from the Anthropic console.
# An OAuth token comes from `claude setup-token` and uses a Claude subscription.
MODEL_ACCESS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

TOOLS = {
    "test_writer": ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
    "builder": ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
    "planner": ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
    "reviewer": ["Read", "Grep", "Glob"],
    "advisor": ["Read", "Grep", "Glob"],
}
READ_ONLY = ("reviewer", "advisor")


class RoleError(RuntimeError):
    pass


class RoleTimeout(RoleError):
    """The role ran past its time."""


@dataclass
class Answer:
    data: dict
    cost_usd: float
    seconds: float
    text: str = field(repr=False, default="")


def prompt(role: str, inputs: dict, lens: str | None = None) -> str:
    parts = [(ROLES / f"{role}.md").read_text()]
    if lens:
        parts.append((LENSES / f"{lens}.md").read_text())
    parts.append("## Inputs\n\n```json\n" + json.dumps(inputs, indent=2) + "\n```\n")
    return "\n\n".join(parts)


def last_block(text: str) -> dict:
    blocks = FENCE.findall(text or "")
    if not blocks:
        raise RoleError("the answer has no ```json block")
    try:
        data = json.loads(blocks[-1])
    except json.JSONDecodeError as err:
        raise RoleError(f"the last ```json block is not valid JSON: {err}") from None
    if not isinstance(data, dict):
        raise RoleError("the last ```json block is not an object")
    return data


def _under(path: Path, folder: Path) -> bool:
    return path == folder or path.is_relative_to(folder)


def check_mount(workdir: str) -> None:
    """Refuse a folder that holds the key folder or the state folder, or that is in
    the state folder but is not a builder's copy."""
    work = Path(os.path.realpath(workdir))
    keys = Path(os.path.realpath(state.key_dir()))
    root = Path(os.path.realpath(state.state_dir(workdir).parent))
    if _under(work, keys) or _under(keys, work):
        raise RoleError(f"{work} holds the key folder; it is never mounted")
    if _under(root, work):
        raise RoleError(f"{work} holds the state folder; it is never mounted")
    if _under(work, root):
        parts = work.relative_to(root).parts
        if len(parts) < 3 or parts[1] != "builders":
            raise RoleError(f"{work} is in the state folder but is not a builder's copy")


def command_line(command: str, role: str, isolation: str = "sandbox", image: str = "",
                 workdir: str = ".", tool: str = "docker", settings_file: str = "",
                 policy: str | None = None) -> list:
    args = shlex.split(command)
    policy = policy or role
    claude = Path(args[0]).name == "claude"
    if claude:
        args += ["--output-format", "json", "--allowedTools", ",".join(TOOLS[policy])]
    if isolation != "container":
        if claude and settings_file:
            args += ["--settings", settings_file]
        return args
    if not image:
        raise RoleError("isolation is container but container_image is empty")
    check_mount(workdir)
    if claude:
        from hooks import policy as pol
        # Inside the container the copy is /work, and Tollgate's code is not there,
        # so the rules go in without the hook.
        rules = pol.settings_for(policy, "/work", "", sandbox=False, hook=False)
        args += ["--settings", json.dumps(rules, sort_keys=True)]
    # No git credentials go in. Only model access goes in, by name, from the
    # driver's environment, and only if set.
    access = [x for name in model_access() for x in ("-e", name)]
    mount = f"{os.path.abspath(workdir)}:/work" + (":ro" if policy in READ_ONLY else "")
    return [tool, "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", mount, "-w", "/work", *access, "-e", "HOME=/tmp", image, *args]


def model_access() -> list:
    """The model access variables that are set and not empty."""
    return [name for name in MODEL_ACCESS if os.environ.get(name)]


def drop_empty_access() -> None:
    """A missing secret may be set to an empty string. Claude Code may read an
    empty ANTHROPIC_API_KEY as a key and skip the OAuth token, so unset it."""
    for name in MODEL_ACCESS:
        if name in os.environ and not os.environ[name]:
            del os.environ[name]


def _settings_file(policy: str, workdir: str, project: str | None, folder: str) -> str:
    """Write the role's Claude Code settings file outside the copy. Return its path."""
    from hooks import policy as pol
    if project:
        path = state.path(project, "run", f"{Path(workdir).name}-{policy}.settings.json")
    else:
        path = Path(folder, f"{policy}.settings.json")
    return pol.write(policy, workdir, project or "", str(path))


def run(command: str, role: str, inputs: dict, workdir: str, minutes: float,
        lens: str | None = None, isolation: str = "sandbox", image: str = "",
        project: str | None = None, policy: str | None = None) -> Answer:
    """Run one role session. policy names the permission set: the role, or
    "planner" for the builder when it writes a plan."""
    policy = policy or role
    with tempfile.TemporaryDirectory() as scratch:
        settings_file = ""
        if isolation == "sandbox" and Path(shlex.split(command)[0]).name == "claude":
            settings_file = _settings_file(policy, workdir, project, scratch)
        args = command_line(command, role, isolation, image, workdir,
                            settings_file=settings_file, policy=policy)
        started = time.monotonic()
        try:
            proc = subprocess.run(args, input=prompt(role, inputs, lens), cwd=workdir,
                                  capture_output=True, text=True, timeout=minutes * 60,
                                  check=False)
        except subprocess.TimeoutExpired:
            raise RoleTimeout(f"{role} ran past {minutes} minutes") from None
    seconds = time.monotonic() - started
    if proc.returncode != 0:
        # Claude Code reports some errors on standard output, as JSON.
        said = (proc.stderr.strip() or proc.stdout.strip())[-500:] or "no output"
        raise RoleError(f"{role} ended with {proc.returncode}: {said}")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RoleError(f"{role} did not print JSON: {proc.stdout.strip()[-300:]}") from None
    if out.get("is_error"):
        raise RoleError(f"{role} reported an error: {str(out.get('result', ''))[-500:]}")
    text = out.get("result", "")
    return Answer(last_block(text), float(out.get("total_cost_usd") or 0), seconds, text)


# The builder's copy.

def copy_path(project: str, name: str) -> Path:
    return state.path(project, "builders", name)


def make_copy(project: str, name: str) -> str:
    """The copy of the project for one ticket or task, in the state folder's
    builders/<name>/. It has no remote: nothing in it can push. The driver keeps
    its `main` up to date and fetches the finished work from it."""
    work = copy_path(project, name)
    if not work.exists():
        subprocess.run(["git", "clone", "-q", "--no-hardlinks", os.path.abspath(project),
                        str(work)], check=True, capture_output=True)
        subprocess.run(["git", "remote", "remove", "origin"], cwd=work, check=True,
                       capture_output=True)
        return str(work)
    head = subprocess.run(["git", "symbolic-ref", "-q", "--short", "HEAD"], cwd=work,
                          capture_output=True, text=True, check=False).stdout.strip()
    if head != "main":
        subprocess.run(["git", "fetch", "-q", os.path.abspath(project),
                        "+refs/heads/main:refs/heads/main"], cwd=work, check=True,
                       capture_output=True)
    return str(work)


def remove_copy(project: str, name: str) -> None:
    shutil.rmtree(copy_path(project, name), ignore_errors=True)
