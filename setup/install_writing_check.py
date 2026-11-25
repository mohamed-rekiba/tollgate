"""Install the writing check in a project, from the project's root folder.

It copies setup/check_writing.py to .tollgate/checks/check_writing.py, adds the
check "writing" to .tollgate/settings.json, and marks the copy as harness, so a
change cannot weaken the check that judges it. The check runs with uv
(`uv run --no-project python`), like Tollgate's hooks. A writing check that an older
Tollgate added with python3 is rewritten with uv, and only that command changes: the
rest of the settings file stays as it is, byte for byte. Running it twice gives the
same files. It prints each path that changed.
"""

import argparse
import json
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "check_writing.py"
TARGET = ".tollgate/checks/check_writing.py"
SETTINGS = ".tollgate/settings.json"
CHECK = {"run": f"uv run --no-project python {TARGET}"}
OLD_RUN = f"python3 {TARGET}"


def migrate(path: Path) -> bool:
    """Rewrite the command of an older writing check in place. Return True when it changed."""
    text = path.read_text()
    old = json.dumps(OLD_RUN)
    settings = json.loads(text)
    if settings.get("checks", {}).get("writing", {}).get("run") != OLD_RUN or text.count(old) != 1:
        return False
    path.write_text(text.replace(old, json.dumps(CHECK["run"])))
    return True


def install(project: str = ".") -> list:
    """Return the paths that changed."""
    changed = []
    target = Path(project, TARGET)
    data = SOURCE.read_bytes()
    if not target.exists() or target.read_bytes() != data:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        changed.append(TARGET)
    path = Path(project, SETTINGS)
    if path.exists() and migrate(path):
        changed.append(SETTINGS)
    settings = json.loads(path.read_text()) if path.exists() else {}
    before = json.dumps(settings, sort_keys=True)
    settings.setdefault("checks", {})["writing"] = CHECK
    harness = settings.setdefault("harness", [])
    if TARGET not in harness:
        harness.append(TARGET)
    if json.dumps(settings, sort_keys=True) != before:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2) + "\n")
        if SETTINGS not in changed:
            changed.append(SETTINGS)
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="install_writing_check", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    args = parser.parse_args(argv)
    try:
        changed = install(args.project)
    except (OSError, ValueError) as err:
        print(f"install_writing_check: {err}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"changed {path}")
    if not changed:
        print("the writing check is already installed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
