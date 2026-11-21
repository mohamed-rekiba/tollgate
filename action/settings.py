"""Load and check the settings file of a project.

The gate always reads the settings from the main branch, so a change cannot
loosen the rules that judge it.
"""

import json
import subprocess
from copy import deepcopy

PATH = ".tollgate/settings.json"

# Paths that are harness in every project, whatever the settings say.
BUILT_IN_HARNESS = [
    ".github/**",
    ".tollgate/settings.json",
    ".tollgate/lenses/**",
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

DEFAULTS = {
    "action": "",
    "setup": [],
    "checks": {},
    "harness": [],
    "tiers": {"3": [], "4": []},
    "tier1": {"max_files": 3, "max_lines": 50},
    "ai": {"builder": "claude -p", "reviewer": "claude -p", "advisor": ["person"]},
    "sandbox": "container",
    "container_image": "",
    "stop": {"attempts": 3, "attempt_minutes": 30, "ticket_usd": 10.0, "task_usd": 60.0},
    "pass_score": 70,
    "require_plan": True,
    "auto_merge": False,
    "check_minutes": 20,
    "approvers": [],
}

CHECK_KEYS = {"run", "report", "minutes"}


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
    if settings["sandbox"] not in ("container", "none"):
        raise SettingsError("sandbox must be container or none")
    for tier in settings["tiers"]:
        if tier not in ("3", "4"):
            raise SettingsError(f"unknown key: tiers.{tier}")
    if settings["sandbox"] == "none":
        settings["auto_merge"] = False
    settings["harness"] = list(settings["harness"]) + BUILT_IN_HARNESS
    return settings


def load_from_ref(repo: str, ref: str) -> dict:
    """Read the settings file as it is at a git ref, for example origin/main."""
    result = subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{PATH}"], capture_output=True, text=True, check=False
    )
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
