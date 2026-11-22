"""Bring a home's shared rules into each project, as a local branch and a ready change.

    python3 -m setup.sync_rules [--home .]

The shared rules are the lens files in the home's rules/lenses/. Each project
gets them in .tollgate/lenses/ on the branch tollgate-sync, made from main in a
separate worktree, so your working folder does not change. It is a change made
by hand, with no ticket: you approve it and merge it with /tollgate:merge.
Tollgate can make a rule stricter. Only you make a rule looser, so nothing
merges on its own.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from gate.store import Store
from setup.home import git, load

BRANCH = "tollgate-sync"
TICKET = "sync-rules"
SUBJECT = "chore(rules): bring the shared rules from the home"


def sync_one(path: Path, lenses: list, store=Store) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp, "work")
        git(path, "worktree", "add", "-q", "--detach", str(work), "main")
        try:
            target = work / ".tollgate" / "lenses"
            target.mkdir(parents=True, exist_ok=True)
            for lens in lenses:
                shutil.copyfile(lens, target / lens.name)
            git(work, "add", "-A", ".tollgate/lenses")
            if not git(work, "status", "--porcelain", "--", ".tollgate/lenses"):
                return "already in sync"
            # --no-verify: the locked-file check refuses any commit to .tollgate/. The
            # change still reaches main only through your merge.
            git(work, "commit", "-q", "--no-verify", "-m", SUBJECT)
            old = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{BRANCH}^{{tree}}"],
                                 cwd=path, capture_output=True, text=True, check=False)
            if old.stdout.strip() == git(work, "rev-parse", "HEAD^{tree}"):
                return f"already a ready change on the branch {BRANCH}"
            git(work, "branch", "-f", BRANCH, "HEAD")
        finally:
            git(path, "worktree", "remove", "--force", str(work))
    return f"the branch {BRANCH} waits for your approval: /tollgate:merge"


def sync(home: str, store=Store) -> list:
    data = load(home)
    lenses = sorted(Path(home, "rules", "lenses").glob("*.md"))
    return [{"project": p["name"], "result": sync_one(Path(home, p["path"]), lenses, store)}
            for p in data["projects"]]


def main(argv=None, store=Store) -> int:
    parser = argparse.ArgumentParser(prog="sync_rules", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=".")
    args = parser.parse_args(argv)
    try:
        for line in sync(args.home, store):
            print(json.dumps(line))
    except subprocess.CalledProcessError as err:
        print(f"sync_rules: {err.stderr or err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
