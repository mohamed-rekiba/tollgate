"""Where Tollgate keeps its state: outside the project, where no AI role can write.

    state_dir(project)   ~/.local/state/tollgate/<name>-<hash>/  (Linux)
                         ~/Library/Application Support/tollgate/<name>-<hash>/  (macOS)
    key_dir()            ~/.config/tollgate/

The state folder holds:

    locks/<ticket>.json and .sig       a signed lock of a ticket's tests
    plans/<task>.json and .sig         a signed lock of an approved plan
    passes/<commit>.json and .sig      a signed record that a commit passed the gate
    approvals/<commit>.json and .sig   your signed approval of a tier 3 or 4 change
    questions/<n>.json                 a question for you, and your answer
    builders/<ticket>/                 the builder's copy of the project
    logs/  reports/  lessons/  run/    the driver's logs, reports, lessons, run locks

TOLLGATE_STATE and TOLLGATE_KEYS override the two roots, for tests.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

KINDS = ("locks", "plans", "passes", "approvals", "questions", "builders", "logs", "reports",
         "lessons", "run")


def _root() -> Path:
    if os.environ.get("TOLLGATE_STATE"):
        return Path(os.environ["TOLLGATE_STATE"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "tollgate"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "tollgate"


def key_dir() -> Path:
    """The folder of this machine's Tollgate key."""
    if os.environ.get("TOLLGATE_KEYS"):
        return Path(os.environ["TOLLGATE_KEYS"])
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "tollgate"


def state_dir(project: str) -> Path:
    """The state folder of one project. Two projects with the same name get two folders."""
    real = os.path.realpath(project)
    tag = hashlib.sha256(real.encode()).hexdigest()[:10]
    return _root() / f"{Path(real).name}-{tag}"


def path(project: str, kind: str, *parts: str) -> Path:
    """A path in the state folder. kind is one of KINDS. The folder is created."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind of state: {kind}")
    folder = state_dir(project) / kind
    folder.mkdir(parents=True, exist_ok=True)
    return folder.joinpath(*parts)


def dumps(record: dict) -> bytes:
    """The exact bytes that are signed: JSON with sorted keys and a final newline."""
    return (json.dumps(record, sort_keys=True, indent=1) + "\n").encode()
