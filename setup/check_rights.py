"""Report which level of rights you have on a repository.

admin   You can make the gate required and lock the tags. Full protection.
write   The freeze and the gate run and show pass or fail. Nothing forces a
        merge to wait, so Tollgate turns auto_merge off.
copy    The organization allows only actions from inside the repository.
        Tollgate's code is copied into .tollgate/runner/ ("version": "copy").
none    You cannot push to the repository. Tollgate cannot be set up.
"""

import argparse
import json
import sys

from setup.gh import Gh, GhError


def level(gh, repository: str) -> dict:
    repo = gh.get(f"repos/{repository}")
    rights = repo.get("permissions") or {}
    if not (rights.get("admin") or rights.get("maintain") or rights.get("push")):
        return {"level": "none", "reason": "you have no write access"}
    allowed = "all"
    try:
        allowed = gh.get(f"repos/{repository}/actions/permissions").get("allowed_actions", "all")
    except GhError:
        pass  # Only admins may read this. A write user finds out when the first run starts.
    if allowed == "local_only":
        return {"level": "copy", "reason": "the repository allows only local actions"}
    if rights.get("admin"):
        return {"level": "admin", "reason": "you can set rulesets"}
    return {"level": "write", "reason": "you can push but cannot set rulesets"}


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="check_rights", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository", help="owner/name")
    args = parser.parse_args(argv)
    try:
        found = level(gh or Gh(), args.repository)
    except GhError as err:
        print(json.dumps({"level": "none", "reason": str(err)}))
        return 1
    print(json.dumps(found))
    return 0 if found["level"] != "none" else 1


if __name__ == "__main__":
    sys.exit(main())
