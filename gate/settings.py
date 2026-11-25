"""Load and check the settings file of a project.

The gate always reads the settings from the main branch, so a change cannot
loosen the rules that judge it.
"""

import json
import subprocess
from copy import deepcopy
from pathlib import PureWindowsPath

PATH = ".tollgate/settings.json"

# Paths that are harness in every project, whatever the settings say.
BUILT_IN_HARNESS = [
    ".github/**",
    ".tollgate/settings.json",
    ".tollgate/lenses/**",
    ".tollgate/checks/**",
    "**/.pre-commit-config.yaml",
    ".tollgate/runner/**",
    "**/conftest.py",
    "**/pytest.ini",
    "**/pyproject.toml",
    "**/setup.cfg",
    "**/setup.py",
    "**/tox.ini",
    "**/noxfile.py",
    "**/.coveragerc",
    "**/package.json",
    "**/jest.config.*",
    "**/vitest.config.*",
    "**/karma.conf.*",
    "**/.mocharc*",
    "**/go.mod",
    "**/go.sum",
    "**/Cargo.toml",
    "**/Cargo.lock",
    "**/requirements*.txt",
    "**/*.lock",
    "**/package-lock.json",
    "**/pnpm-lock.yaml",
]

# The image a role runs in for background mode with the container isolation: Docker's
# own Claude Code image, with git, Python, Node, and Go, pinned to one build by its
# digest. A weekly workflow (.github/workflows/image-bump.yml) proposes a newer build
# once it passes tests/proof_container.py. Set "container_image" to use another image.
DEFAULT_IMAGE = ("docker/sandbox-templates:claude-code@sha256:"
                 "30ec2b1bb76e3993aff912c553a5c249ad95b595249a32fde7158eafb71bda25")

DEFAULTS = {
    "setup": [],
    "checks": {},
    "harness": [],
    "tiers": {"3": [], "4": []},
    "tier1": {"max_files": 3, "max_lines": 50},
    "ai": {"builder": "claude -p", "reviewer": "claude -p", "advisor": ["person"],
           "stronger_builder": ""},
    "container_image": DEFAULT_IMAGE,
    "stop": {"attempts": 3, "attempt_minutes": 30, "ticket_usd": 10.0, "task_usd": 60.0},
    "pass_score": 70,
    # Who runs each role: "session" (your own Claude Code session starts each role as a
    # subagent, through driver.step) or "background" (the driver starts each role as its
    # own process, in its isolation).
    "runner": "session",
    # How the background driver keeps a role apart: "container" (Docker) or "sandbox"
    # (Claude Code's). Session mode does not use it.
    "isolation": "container",
    # The files and folders, relative to the project root, that state the intended design.
    # The analyst reads them first, and a fact from them is "specified".
    "spec": [],
    "require_plan": True,
    "auto_merge": False,
    # Where the driver asks the advisor before it goes on. The names are "plan",
    # "ticket" (after each ready ticket), and "task" (after the review of the whole task).
    "checkpoints": ["plan", "task"],
    # The time limit of a check that sets no "minutes" of its own.
    "check_minutes": 20,
    # How many checks of the pre-push hook run at once: true for all of them, a whole
    # number for that many, false for one at a time. Heavy checks may want fewer.
    "parallel": True,
    # The base suite: one command for each of the five things a base must prove.
    "base": {"checks_run": "", "parallel_tests": "", "env_up_down": "",
             "bad_setting_stops": "", "one_log_line": ""},
}

CHECK_KEYS = {"run", "report", "minutes"}
CHECKPOINTS = ("plan", "ticket", "task")
ISOLATIONS = ("container", "sandbox")
RUNNERS = ("session", "background")


class SettingsError(ValueError):
    """The settings file cannot be used. The message names the problem."""


def _merge(base, extra, where):
    for key, value in extra.items():
        name = f"{where}.{key}" if where else key
        if key not in base:
            raise SettingsError(f"unknown key: {name}")
        if isinstance(base[key], dict) and key not in ("checks",):
            if not isinstance(value, dict):
                raise SettingsError(f"{name} must be an object")
            _merge(base[key], value, name)
        else:
            base[key] = value


def parse(text: str) -> dict:
    """Return the settings with defaults filled in. Raise SettingsError on a bad file."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as err:
        raise SettingsError(f"not valid JSON: {err}") from None
    if not isinstance(raw, dict):
        raise SettingsError("the settings file must hold one JSON object")
    settings = deepcopy(DEFAULTS)
    _merge(settings, raw, "")
    for name, check in settings["checks"].items():
        if not isinstance(check, dict) or "run" not in check:
            raise SettingsError(f"checks.{name} needs a run command")
        extra = set(check) - CHECK_KEYS
        if extra:
            raise SettingsError(f"unknown key: checks.{name}.{min(extra)}")
    points = settings["checkpoints"]
    if not isinstance(points, list) or any(p not in CHECKPOINTS for p in points):
        raise SettingsError(f"checkpoints must be a list of: {', '.join(CHECKPOINTS)}")
    if settings["isolation"] not in ISOLATIONS:
        raise SettingsError('isolation must be "container" or "sandbox"')
    if settings["runner"] not in RUNNERS:
        raise SettingsError('runner must be "session" or "background"')
    parallel = settings["parallel"]
    if not (isinstance(parallel, bool) or (isinstance(parallel, int) and parallel >= 1)):
        raise SettingsError("parallel must be true, false, or a whole number of 1 or more")
    if not isinstance(settings["spec"], list):
        raise SettingsError("spec must be a list of paths")
    for n, path in enumerate(settings["spec"], 1):
        if not isinstance(path, str) or not path.strip():
            raise SettingsError(f"spec item {n} must be a path")
        if path.startswith(("/", "\\")) or PureWindowsPath(path).is_absolute():
            raise SettingsError(f"spec item {n} must be relative to the project root")
        if ".." in PureWindowsPath(path).parts:
            raise SettingsError(f"spec item {n} must not contain ..")
    for tier in settings["tiers"]:
        if tier not in ("3", "4"):
            raise SettingsError(f"unknown key: tiers.{tier}")
    settings["harness"] = list(settings["harness"]) + BUILT_IN_HARNESS
    return settings


def load_from_ref(repo: str, ref: str) -> dict:
    """Read the settings file as it is at a git ref, for example origin/main."""
    from gate.gitio import safe_env
    # With no replace refs: a role can write them in its copy, and this reads the copy.
    result = subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{PATH}"], capture_output=True, text=True, check=False,
        env=safe_env())
    if result.returncode != 0:
        raise SettingsError(f"{PATH} not found at {ref}")
    return parse(result.stdout)


def main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="tollgate settings",
                                     description="Check a settings file and print it in full.")
    parser.add_argument("path", nargs="?", default=PATH)
    args = parser.parse_args(argv)
    try:
        with open(args.path) as f:
            found = parse(f.read())
    except (OSError, SettingsError, ValueError) as err:
        print(f"{args.path}: {err}", file=sys.stderr)
        return 1
    print(json.dumps(found, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
