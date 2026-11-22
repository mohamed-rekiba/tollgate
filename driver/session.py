"""Who runs a role: the background driver, or your own Claude Code session.

The driver asks for each role through one caller. Python still decides every
step, the gate still scores, and the store still signs and merges; only the
place where the role runs differs.

- Background: the driver starts the role as its own process, in its isolation,
  with driver/roles.py. This is the background driver.
- Session: your own Claude Code session starts the role as one of Tollgate's
  subagents. The caller first looks for a saved answer to the same question:
  the same role, lens, and inputs. If there is one, it returns it. If not, it
  writes the step file, run/step.json in the state folder, and raises Pause.
  The driver then lets go of its run lock and ends with 5. `driver.step answer`
  saves the answer, and the next run of the driver replays its log and the
  saved answers up to the next step.

Each saved answer carries a code made with a secret drawn from the machine key,
and a saved answer whose code does not verify is ignored. A role cannot read the
key folder, so a line a role writes into the answers file counts for nothing.

A role that writes, the builder or the test writer, leaves its work in the
copy. Its answer saves that work as a commit on refs/tollgate/answers/<key> in
the copy, and a replay puts the work back, because each try starts again from
the best try so far.
"""

import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from driver import roles
from gate import settings as st
from gate import sign, state

WRITERS = ("builder", "test_writer")
ANSWERS = ".answers.jsonl"
INIT = "Run /tollgate:init in this project first."


class Pause(Exception):
    """A role waits for your session. The step file says which role and with what."""

    def __init__(self, step: dict):
        super().__init__(f"the {step['role']} waits for your session")
        self.step = step


class NotReady(st.SettingsError):
    """A task cannot pass the gate here: no signers on main, or no machine key."""


@dataclass
class Call:
    """One role the driver needs. log names the log of the ticket or the task."""
    role: str
    inputs: dict
    lens: str | None
    command: str
    policy: str
    copy: str
    project: str
    log: str
    ticket: str = ""
    task: str = ""


def key(role: str, lens: str | None, inputs: dict) -> str:
    """The name of one question to a role: the same role, lens, and inputs give the same key."""
    data = json.dumps([role, lens or "", inputs], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def step_path(project: str) -> Path:
    return state.path(project, "run", "step.json")


def answers_path(project: str, log: str) -> Path:
    return state.path(project, "logs", f"{log}{ANSWERS}")


STEP_FIELDS = ("role", "key", "log", "task", "prompt")


def read_step(project: str) -> dict | None:
    """The step that waits, or None when there is none or the file is not a step."""
    try:
        found = json.loads(step_path(project).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(found, dict) or not all(isinstance(found.get(f), str) and found.get(f)
                                              for f in STEP_FIELDS if f != "task"):
        return None
    if not isinstance(found.get("task", ""), str) or not isinstance(found.get("copy", ""), str):
        return None
    return found


def _write_step(project: str, step: dict) -> None:
    path = step_path(project)
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(step, indent=1) + "\n")
    os.replace(tmp, path)


def digest(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def new_nonce(project: str) -> str:
    """A new nonce for the step that waits. Only its hash goes in the step file; the
    nonce itself goes to your session in next's output, and answer needs it."""
    step = read_step(project)
    if step is None:
        raise roles.RoleError("no step waits")
    nonce = secrets.token_hex(16)
    step["nonce_sha256"] = digest(nonce)
    _write_step(project, step)
    return nonce


def clear_step(project: str) -> None:
    step_path(project).unlink(missing_ok=True)


def _mac(line: dict) -> str:
    """A code over a saved answer, made with a secret drawn from the machine key. A role
    cannot read the key folder, so it cannot make a saved answer that verifies."""
    import hmac
    secret = hashlib.sha256(b"tollgate-answers\0" + sign.machine_key().read_bytes()).digest()
    data = json.dumps([line.get(k) for k in ("key", "role", "lens", "seconds", "work", "text")],
                      separators=(",", ":"))
    return hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()


def _verifies(line: dict) -> bool:
    import hmac
    try:
        return isinstance(line.get("mac"), str) and hmac.compare_digest(line["mac"], _mac(line))
    except OSError:
        return False


def saved(project: str, log: str, found_key: str) -> dict | None:
    """The last saved answer with this key that verifies, or None."""
    from driver.log import read
    found = [a for a in read(str(answers_path(project, log)))
             if a.get("key") == found_key and _verifies(a)]
    return found[-1] if found else None


def _git(cwd: str, *args, env=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def work_ref(found_key: str) -> str:
    return f"refs/tollgate/answers/{found_key}"


def save_work(copy: str, found_key: str) -> str:
    """Save the copy's work tree as a commit on work_ref(key), with HEAD as its parent.
    HEAD, the index, and the work tree do not change. Return the commit."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp, "index"))}
        _git(copy, "read-tree", "HEAD", env=env)
        _git(copy, "add", "-A", env=env)
        tree = _git(copy, "write-tree", env=env)
    commit = _git(copy, "commit-tree", tree, "-p", "HEAD", "-m",
                  f"tollgate: the work of the answer {found_key[:12]}")
    _git(copy, "update-ref", work_ref(found_key), commit)
    return commit


def restore_work(copy: str, found_key: str) -> bool:
    """Put the saved work back in the copy's work tree, on top of HEAD. False when the
    copy holds no such work, for example a copy made again."""
    ref = work_ref(found_key)
    done = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{ref}^{{tree}}"], cwd=copy,
                          capture_output=True, text=True, check=False)
    if done.returncode:
        return False
    _git(copy, "read-tree", "--reset", "-u", ref)
    _git(copy, "reset", "-q")
    return True


def save_answer(project: str, step: dict, text: str) -> dict:
    """Save your session's answer to the step. Raise roles.RoleError when the answer
    has no final json block. The step file goes once the answer is saved."""
    roles.last_block(text)
    work = ""
    if step["role"] in WRITERS and step.get("copy"):
        work = save_work(step["copy"], step["key"])
    line = {"key": step["key"], "role": step["role"], "lens": step.get("lens"),
            "seconds": round(max(0.0, time.time() - float(step.get("asked_at") or time.time())),
                             1), "work": work, "text": text}
    line["mac"] = _mac(line)
    from driver.log import Log
    with Log(str(answers_path(project, step["log"]))) as log:
        log.add("answer", **line)
    clear_step(project)
    return line


class Background:
    """The background driver's caller: the role runs as its own process."""

    def __init__(self, settings: dict):
        self.settings = settings

    def __call__(self, call: Call) -> roles.Answer:
        s = self.settings
        return roles.run(call.command, call.role, call.inputs, call.copy,
                         s["stop"]["attempt_minutes"], call.lens, s["isolation"],
                         s["container_image"], call.project, call.policy)


class Session:
    """Session mode's caller: a saved answer, or a step for your session and a Pause.
    The cost of a role is not known here, so the answer's cost is None."""

    def __call__(self, call: Call) -> roles.Answer:
        found_key = key(call.role, call.lens, call.inputs)
        found = saved(call.project, call.log, found_key)
        if found and (not found.get("work") or restore_work(call.copy, found_key)):
            text = found["text"]
            return roles.Answer(roles.last_block(text), None, float(found.get("seconds") or 0),
                                text)
        step = {"agent": f"tollgate:{call.role}", "role": call.role, "policy": call.policy,
                "lens": call.lens, "prompt": roles.prompt(call.role, call.inputs, call.lens),
                "copy": os.path.realpath(call.copy) if call.copy else "", "key": found_key,
                "log": call.log, "ticket": call.ticket, "task": call.task,
                "asked_at": time.time()}
        _write_step(call.project, step)
        raise Pause(step)


def caller(settings: dict, runner: str | None = None):
    """The caller for the runner named, or else for the setting `runner`."""
    return Session() if (runner or settings["runner"]) == "session" else Background(settings)


def cannot_pass(project: str) -> str:
    """Why a task cannot pass the gate here, or "": the settings on main must name
    signers, and this machine must have its machine key."""
    try:
        found = st.load_from_ref(project, "main")
    except st.SettingsError as err:
        return f"the settings on main cannot be read: {err}. {INIT}"
    if not found["signers"]:
        return f"signers in the settings on main is empty, so no lock or pass record can verify. {INIT}"
    if not sign.machine_key().exists():
        return f"this machine has no machine key at {sign.machine_key()}. {INIT}"
    return ""
