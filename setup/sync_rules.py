"""Send a home's shared rules to each project, as a pull request in each.

The shared rules are the lens files in the home's rules/lenses/. Each project
gets them in .tollgate/lenses/ on the branch tollgate-sync, and a person merges
the pull request. Tollgate can make a rule stricter. Only a person makes a rule
looser, so nothing merges on its own.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from setup.gh import Gh
from setup.home import HomeError, git, load

BRANCH = "tollgate-sync"


def sync(home: str, gh=None, push=True) -> list:
    data = load(home)
    lenses = sorted(Path(home, "rules", "lenses").glob("*.md"))
    out = []
    for project in data["projects"]:
        path = Path(home, project["path"])
        git(path, "fetch", "-q", "origin")
        git(path, "checkout", "-q", "-B", BRANCH, "origin/main")
        target = Path(path, ".tollgate", "lenses")
        target.mkdir(parents=True, exist_ok=True)
        for lens in lenses:
            shutil.copyfile(lens, target / lens.name)
        git(path, "add", "-A", ".tollgate/lenses")
        if not git(path, "status", "--porcelain", "--", ".tollgate/lenses"):
            out.append({"project": project["name"], "result": "already in sync"})
            continue
        git(path, "commit", "-q", "-m", "tollgate: sync the shared rules from the home")
        if push:
            git(path, "push", "-q", "-f", "origin", BRANCH)
            pr = (gh or Gh()).api("POST", f"repos/{project['name']}/pulls", {
                "title": "Tollgate: shared rules from the home", "head": BRANCH, "base": "main",
                "body": "The lens files from the home. A person reviews and merges this."})
            out.append({"project": project["name"], "result": f"pull request #{pr['number']}"})
        else:
            out.append({"project": project["name"], "result": "committed, not pushed"})
    return out


def check(home: str) -> list:
    """Names of the projects whose .tollgate/lenses differ from the home's lenses.

    Read-only: it compares the files in each project's working tree and runs no git.
    A lens differs if it is missing or has other content. Extra lenses that only the
    project has are not a difference, because sync never removes them.
    """
    data = load(home)
    lenses = sorted(Path(home, "rules", "lenses").glob("*.md"))
    differ = []
    for project in data["projects"]:
        target = Path(home, project["path"], ".tollgate", "lenses")
        if any(not (target / lens.name).is_file()
               or (target / lens.name).read_bytes() != lens.read_bytes() for lens in lenses):
            differ.append(project["name"])
    return differ


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="sync_rules", description=__doc__)
    parser.add_argument("--home", default=".")
    parser.add_argument("--check", action="store_true",
                        help="list the projects whose lenses differ; change nothing; exit 1 if any")
    args = parser.parse_args(argv)
    if args.check:
        try:
            differ = check(args.home)
        except (HomeError, OSError) as err:
            print(f"sync_rules: {err}", file=sys.stderr)
            return 2
        for name in differ:
            print(name)
        return 1 if differ else 0
    try:
        for line in sync(args.home, gh):
            print(json.dumps(line))
    except subprocess.CalledProcessError as err:
        print(f"sync_rules: {err.stderr or err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
