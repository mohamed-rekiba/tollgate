"""Write the Tollgate workflows into a project, pinned to one commit of Tollgate.

Running it twice gives the same files. It ends by reading the files back.
"""

import argparse
import re
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "workflows"
PLACEHOLDER = "__TOLLGATE_REF__"
SHA = re.compile(r"^[0-9a-f]{40}$")


def render(ref: str) -> dict:
    if not SHA.match(ref):
        raise ValueError("pin Tollgate to a full commit id, not a branch or a tag")
    return {f".github/workflows/{t.name}": t.read_text().replace(PLACEHOLDER, ref)
            for t in sorted(TEMPLATES.glob("tollgate-*.yml"))}


def write(project: str, ref: str) -> list:
    """Write the files. Return the paths that changed."""
    changed = []
    for path, text in render(ref).items():
        target = Path(project, path)
        if target.exists() and target.read_text() == text:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        changed.append(path)
    for path, text in render(ref).items():
        if Path(project, path).read_text() != text:
            raise RuntimeError(f"{path} does not hold what was written")
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="write_workflows", description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--ref", required=True, help="full commit id of Tollgate to pin")
    args = parser.parse_args(argv)
    try:
        changed = write(args.project, args.ref)
    except (ValueError, RuntimeError, OSError) as err:
        print(f"write_workflows: {err}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"wrote {path}")
    if not changed:
        print("the workflows are already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
