"""Say what is missing for Tollgate's two layers of rules in a project.

    python3 -m setup.health [--project .]

It prints one warning for each missing part, and ends with 1 when there is one:

- pre-commit is not installed, the project has no .pre-commit-config.yaml, or
  a git hook of pre-commit is not installed;
- a check in .tollgate/checks/ is missing or differs from the plugin's copy;
- the plugin has no Claude Code hooks file, hooks/hooks.json.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from setup import precommit

PLUGIN = Path(__file__).resolve().parent.parent
FIX = "Run /tollgate:init."


def hooks_dir(root: Path) -> Path:
    proc = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
                          cwd=root, capture_output=True, text=True, check=False)
    return Path(proc.stdout.strip()) if proc.returncode == 0 else root / ".git" / "hooks"


def warnings(project: str = ".", which=shutil.which, plugin: Path = PLUGIN) -> list:
    root = Path(project).resolve()
    found = []
    if not which("pre-commit"):
        found.append("pre-commit is not installed, so no check runs before a commit. "
                     "Install it: pipx install pre-commit")
    if not (root / precommit.CONFIG).exists():
        found.append(f"{precommit.CONFIG} is missing. {FIX}")
    folder = hooks_dir(root)
    for kind in precommit.HOOK_TYPES:
        hook = folder / kind
        if not hook.exists() or "pre-commit" not in hook.read_text(errors="replace"):
            found.append(f"the git hook {kind} is not installed. {FIX}")
    for name in precommit.SCRIPTS:
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
