"""Say what is missing for Tollgate's two layers of rules in a project.

    python3 -m setup.health [--project .]

It prints one warning for each missing part, and ends with 1 when there is one:

- uv or pre-commit is not installed, the project has no .pre-commit-config.yaml, it
  or .tollgate/settings.json still runs a Tollgate check with python3 instead of uv, or a
  git hook of pre-commit is not installed;
- a check in .tollgate/checks/ is missing or differs from the plugin's copy;
- a check under `checks` in .tollgate/settings.json names a hook that is not in
  .pre-commit-config.yaml, or still keeps a project command under `run`;
- the plugin has no Claude Code hooks file, hooks/hooks.json.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from gate import precommit_config as pc
from setup import precommit

PLUGIN = Path(__file__).resolve().parent.parent
FIX = "Run /tollgate:init."


def hooks_dir(root: Path) -> Path:
    proc = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
                          cwd=root, capture_output=True, text=True, check=False)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else root / ".git" / "hooks"


def check_hooks(root: Path) -> list:
    """A warning for each check of the settings whose hook the config does not have, and
    for each that still keeps a project command under `run`."""
    try:
        checks = json.loads((root / precommit.SETTINGS).read_text()).get("checks", {})
    except (OSError, ValueError, AttributeError):
        return []
    config = root / precommit.CONFIG
    have = pc.hook_ids(config.read_text(errors="replace")) if config.exists() else []
    found = []
    for name, check in sorted(checks.items()) if isinstance(checks, dict) else []:
        if not isinstance(check, dict):
            continue
        if "hook" in check and check["hook"] not in have:
            found.append(f"the check {name} names the hook {check['hook']}, which is not in "
                         f"{precommit.CONFIG}, so the gate cannot run it. Add the hook, or "
                         f"name another in {precommit.SETTINGS}.")
        elif "run" in check and name != precommit.OWN_CHECK:
            found.append(f"the check {name} keeps its command in {precommit.SETTINGS}. {FIX} "
                         f"It moves the command into a hook of {precommit.CONFIG}.")
    return found


def warnings(project: str = ".", which=shutil.which, plugin: Path = PLUGIN) -> list:
    root = Path(project).resolve()
    found = []
    if not which("uv"):
        found.append("uv is not installed, so the Tollgate checks cannot run before a commit. "
                     "Install it: brew install uv, or see https://docs.astral.sh/uv/")
    if not which("pre-commit"):
        found.append("pre-commit is not installed, so no check runs before a commit. "
                     "Install it: uv tool install pre-commit")
    config = root / precommit.CONFIG
    if not config.exists():
        found.append(f"{precommit.CONFIG} is missing. {FIX}")
    elif "python3 .tollgate/checks/" in config.read_text(errors="replace"):
        found.append(f"{precommit.CONFIG} runs a check with python3, not uv. {FIX}")
    settings = root / precommit.SETTINGS
    if settings.exists() and "python3 .tollgate/checks/" in settings.read_text(errors="replace"):
        found.append(f"{precommit.SETTINGS} runs a Tollgate check with python3, not uv. {FIX}")
    found += check_hooks(root)
    folder = hooks_dir(root)
    for kind in precommit.HOOK_TYPES:
        hook = folder / kind
        if not hook.exists() or "pre-commit" not in hook.read_text(errors="replace"):
            found.append(f"the git hook {kind} is not installed. {FIX}")
    for name in () if precommit.is_tollgate(root) else precommit.SCRIPTS:
        copy = root / precommit.CHECKS_DIR / name
        if not copy.exists():
            found.append(f"{precommit.CHECKS_DIR}/{name} is missing. {FIX}")
        elif copy.read_bytes() != (precommit.HERE / name).read_bytes():
            found.append(f"{precommit.CHECKS_DIR}/{name} differs from the plugin's copy. {FIX}")
    if not (plugin / "hooks" / "hooks.json").exists():
        found.append("the plugin has no Claude Code hooks, so no rule stops a role before it "
                     "acts. Update the plugin.")
    return found


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="health", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    args = parser.parse_args(argv)
    found = warnings(args.project)
    for line in found:
        print(f"warning: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
