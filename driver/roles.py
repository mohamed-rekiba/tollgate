"""The role runner, the builder's copy, and the container.

A role is one AI session. The runner sends the role file and the inputs on
standard input and reads one JSON answer. The command comes from the settings.
Claude Code gets its flags. Any other command is a fake role with the same
contract: read the prompt on standard input, print {"result": ..., "total_cost_usd": ...}.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

ROLES = Path(__file__).resolve().parent.parent / "roles"
LENSES = Path(__file__).resolve().parent.parent / "lenses"
FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

TOOLS = {
    "test_writer": ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
    "builder": ["Read", "Grep", "Glob", "Write", "Edit", "Bash"],
    "reviewer": ["Read", "Grep", "Glob"],
    "advisor": ["Read", "Grep", "Glob"],
}


class RoleError(RuntimeError):
    pass


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


def command_line(command: str, role: str, sandbox: str = "none", image: str = "",
                 workdir: str = ".", tool: str = "docker") -> list:
    args = shlex.split(command)
    if Path(args[0]).name == "claude":
        args += ["--output-format", "json", "--allowedTools", ",".join(TOOLS[role])]
    if sandbox != "container":
        return args
    if not image:
        raise RoleError("sandbox is container but container_image is empty")
    # No git or gh credentials go in, so a push from inside fails. Only the
    # model key goes in, by name, from the driver's environment.
    return [tool, "run", "--rm", "-i", "--user", f"{os.getuid()}:{os.getgid()}",
            "-v", f"{os.path.abspath(workdir)}:/work", "-w", "/work",
            "-e", "ANTHROPIC_API_KEY", "-e", "HOME=/tmp", image, *args]


def run(command: str, role: str, inputs: dict, workdir: str, minutes: float,
        lens: str | None = None, sandbox: str = "none", image: str = "") -> Answer:
    args = command_line(command, role, sandbox, image, workdir)
    started = time.monotonic()
    try:
        proc = subprocess.run(args, input=prompt(role, inputs, lens), cwd=workdir,
                              capture_output=True, text=True, timeout=minutes * 60, check=False)
    except subprocess.TimeoutExpired:
        raise RoleError(f"{role} ran past {minutes} minutes") from None
    seconds = time.monotonic() - started
    if proc.returncode != 0:
        raise RoleError(f"{role} ended with {proc.returncode}: {proc.stderr.strip()[-500:]}")
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RoleError(f"{role} did not print JSON") from None
    text = out.get("result", "")
    return Answer(last_block(text), float(out.get("total_cost_usd") or 0), seconds, text)


def make_copy(project: str, ticket: str) -> str:
    """A fresh clone of the project for one ticket, in .tollgate/work/<ticket>."""
    work = Path(project, ".tollgate", "work", ticket)
    if work.exists():
        return str(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", os.path.abspath(project), str(work)],
                   check=True, capture_output=True)
    origin = subprocess.run(["git", "remote", "get-url", "origin"], cwd=project,
                            capture_output=True, text=True, check=False).stdout.strip()
    if origin:
        subprocess.run(["git", "remote", "set-url", "origin", origin], cwd=work, check=True)
    return str(work)


def remove_copy(project: str, ticket: str) -> None:
    shutil.rmtree(Path(project, ".tollgate", "work", ticket), ignore_errors=True)
