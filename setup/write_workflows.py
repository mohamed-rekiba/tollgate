"""Write the Tollgate workflow into a project, and set the Tollgate version.

The workflow file is the same for every version, so it is written once. The
version lives in .tollgate/settings.json under "version": "self" for the
Tollgate repository itself, or a full commit id of Tollgate. An upgrade changes
only that line, as an ordinary pull request.

Running it twice gives the same files. It removes the four workflow files of
older versions. It ends by reading the files back.
"""

import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "workflows" / "tollgate.yml"
WORKFLOW = ".github/workflows/tollgate.yml"
OLD = [f".github/workflows/tollgate-{n}.yml" for n in ("freeze", "gate", "plan", "review")]
SETTINGS = ".tollgate/settings.json"
VERSION = re.compile(r"^(self|[0-9a-f]{40})$")


def write(project: str, version: str) -> list:
    """Write the workflow and the version. Return the paths that changed."""
    if not VERSION.match(version):
        raise ValueError('the version is "self" or a full commit id of Tollgate, not a branch '
                         "or a tag")
    changed = []
    target = Path(project, WORKFLOW)
    text = TEMPLATE.read_text()
    if not target.exists() or target.read_text() != text:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        changed.append(WORKFLOW)
    for old in OLD:
        if Path(project, old).exists():
            Path(project, old).unlink()
            changed.append(old)
    settings_path = Path(project, SETTINGS)
    settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    if settings.get("version") != version:
        settings["version"] = version
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        changed.append(SETTINGS)
    if Path(project, WORKFLOW).read_text() != text:
        raise RuntimeError(f"{WORKFLOW} does not hold what was written")
    if json.loads(settings_path.read_text()).get("version") != version:
        raise RuntimeError(f"{SETTINGS} does not hold the version")
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="write_workflows", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--version", "--ref", dest="version", required=True,
                        help='"self", or a full commit id of Tollgate')
    args = parser.parse_args(argv)
    try:
        changed = write(args.project, args.version)
    except (ValueError, RuntimeError, OSError) as err:
        print(f"write_workflows: {err}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"changed {path}")
    if not changed:
        print("the workflow and the version are already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
