"""Load and check the settings file of a project.

The gate always reads the settings from the main branch, so a change cannot
loosen the rules that judge it.
"""

import base64
import binascii
import json
import subprocess
from copy import deepcopy

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

DEFAULTS = {
    "setup": [],
    "checks": {},
    "harness": [],
    "tiers": {"3": [], "4": []},
    "tier1": {"max_files": 3, "max_lines": 50},
    "ai": {"builder": "claude -p", "reviewer": "claude -p", "advisor": ["person"],
           "stronger_builder": ""},
    "container_image": "",
    "stop": {"attempts": 3, "attempt_minutes": 30, "ticket_usd": 10.0, "task_usd": 60.0},
    "pass_score": 70,
    # The public keys that may sign locks, pass records, and approvals.
    "signers": [],
    # The public SSH keys of the people who may approve a tier 3 or 4 merge. Only these
    # keys verify an approval, so the machine key that signs locks can never approve.
    "owners": [],
    # How the builder is kept apart: "container" (Docker) or "sandbox" (Claude Code's).
    "isolation": "container",
    "require_plan": True,
    "auto_merge": False,
    # The time limit of a check that sets no "minutes" of its own.
    "check_minutes": 20,
    # Paths a change may touch with no ticket: tier 1, and only the checks run.
    "free": ["docs/**", "README.md", "CHANGELOG.md", "LICENSE", "NOTICE"],
    # The base suite: one command for each of the five things a base must prove.
    "base": {"checks_run": "", "parallel_tests": "", "env_up_down": "",
             "bad_setting_stops": "", "one_log_line": ""},
}

CHECK_KEYS = {"run", "report", "minutes"}
ISOLATIONS = ("container", "sandbox")
KEY_TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
             "ecdsa-sha2-nistp521", "sk-ssh-ed25519@openssh.com",
             "sk-ecdsa-sha2-nistp256@openssh.com")


class SettingsError(ValueError):
    """The settings file cannot be used. The message names the problem."""


def is_public_key(line) -> bool:
    """True when line looks like an SSH public key line: type, key, and an optional comment."""
    if not isinstance(line, str) or "\n" in line.strip():
        return False
    parts = line.split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        return False
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError):
        return False
    # The key starts with its own type: a 4-byte length, then the name.
    size = int.from_bytes(blob[:4], "big")
    return blob[4:4 + size] == parts[0].encode()


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
    if settings["isolation"] not in ISOLATIONS:
        raise SettingsError('isolation must be "container" or "sandbox"')
    if not isinstance(settings["signers"], list):
        raise SettingsError("signers must be a list of public key lines")
    for n, line in enumerate(settings["signers"], 1):
        if not is_public_key(line):
            raise SettingsError(f"signers item {n} is not an SSH public key line")
    for key in ("owners",):
        if not isinstance(settings[key], list):
            raise SettingsError(f"{key} must be a list of public key lines")
        for n, line in enumerate(settings[key], 1):
            if not is_public_key(line):
                raise SettingsError(f"{key} item {n} is not an SSH public key line")
    for tier in settings["tiers"]:
        if tier not in ("3", "4"):
            raise SettingsError(f"unknown key: tiers.{tier}")
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
