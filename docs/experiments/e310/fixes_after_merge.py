"""Count the commits that fix or undo a merged change in the 14 days after its merge.

    python3 docs/experiments/e310/fixes_after_merge.py --repo . --merge <merge commit> [--days 14]

A commit counts when it lands on main after the merge, within the days given,
touches a file the change touched, and its message says fix, revert, undo, or
broke. Run it 14 days after each merge. It prints one JSON line.
"""

import argparse
import json
import re
import subprocess
import sys

WORDS = re.compile(r"\b(fix|fixes|fixed|revert|reverts|undo|broke|broken)\b", re.IGNORECASE)


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          check=True).stdout.strip()


def count(repo: str, merge: str, days: int = 14, ref: str = "origin/main") -> dict:
    files = set(git(repo, "show", "--name-only", "--format=", merge).split())
    when = int(git(repo, "show", "-s", "--format=%ct", merge))
    later = git(repo, "log", "--format=%H %ct %s", f"{merge}..{ref}").splitlines()
    hits = []
    for line in later:
        sha, stamp, subject = line.split(" ", 2)
        if int(stamp) - when > days * 86400 or not WORDS.search(subject):
            continue
        touched = set(git(repo, "show", "--name-only", "--format=", sha).split())
        if touched & files:
            hits.append({"commit": sha[:7], "subject": subject})
    return {"merge": merge[:7], "days": days, "fixes": len(hits), "commits": hits}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--merge", required=True)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--ref", default="origin/main", help="the main branch to read")
    args = parser.parse_args(argv)
    print(json.dumps(count(args.repo, args.merge, args.days, args.ref)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
