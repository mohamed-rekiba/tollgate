"""Protect the main branch and lock the tags under tg/.

Main takes changes only through pull requests, and nobody can force-push or
delete it. Nobody can move or delete a tag under tg/.

Needs admin rights. Running it twice gives the same rulesets. It ends by reading
them back. With --print it changes nothing and prints the requests, for you to
hand to an admin.
"""

import argparse
import json
import sys

from setup.gh import Gh, GhError

GITHUB_ACTIONS_APP = 15368
BRANCH_RULESET = "tollgate main"
TAG_RULESET = "tollgate tags"
TAG_PATTERN = "refs/tags/tg/**/*"


def wanted(owner_type: str = "Organization") -> list:
    """owner_type is "User" for a personal account. GitHub accepts an app as a bypass
    actor only in an organization, so a personal repository gets no creation rule."""
    branch = {
        "name": BRANCH_RULESET, "target": "branch", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": {
                "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False, "require_last_push_approval": False,
                "required_review_thread_resolution": False}},
        ],
        "bypass_actors": [],
    }
    # Nobody may move or delete these tags. In an organization, only the freeze
    # and plan workflows, through GitHub Actions, may create them. On a personal
    # account anyone with write access may create one, and the gate rejects any
    # tag that its run did not record (rule 1 and rule 2).
    tags = {
        "name": TAG_RULESET, "target": "tag", "enforcement": "active",
        # GitHub matches with fnmatch and FNM_PATHNAME: a trailing ** covers one
        # level only, so tg/** would miss tg/freeze/<ticket>/<n>. **/* covers all.
        "conditions": {"ref_name": {"include": [TAG_PATTERN], "exclude": []}},
        "rules": [{"type": "update"}, {"type": "deletion"}],
        "bypass_actors": [],
    }
    if owner_type == "Organization":
        tags["rules"].insert(0, {"type": "creation"})
        tags["bypass_actors"] = [{"actor_id": GITHUB_ACTIONS_APP, "actor_type": "Integration",
                                  "bypass_mode": "always"}]
    return [branch, tags]


def _covers(have, want) -> bool:
    """True when `have` holds everything in `want`. GitHub adds default fields when it
    reads a ruleset back, such as allowed_merge_methods, so equality is too strict."""
    if isinstance(want, dict):
        return isinstance(have, dict) and all(k in have and _covers(have[k], v)
                                              for k, v in want.items())
    if isinstance(want, list):
        return (isinstance(have, list) and len(have) == len(want)
                and all(_covers(h, w) for h, w in zip(have, want, strict=True)))
    return have == want


def _same(have: dict, want: dict) -> bool:
    keys = ("target", "enforcement", "conditions", "rules", "bypass_actors")
    return all(_covers(have.get(k), want[k]) for k in keys)


def apply(gh, repository: str) -> list:
    """Create or update both rulesets. Return what it did for each."""
    owner_type = (gh.get(f"repos/{repository}").get("owner") or {}).get("type", "User")
    existing = {r["name"]: r["id"] for r in gh.get(f"repos/{repository}/rulesets") or []}
    done = []
    for rule in wanted(owner_type):
        if rule["name"] in existing:
            path = f"repos/{repository}/rulesets/{existing[rule['name']]}"
            if _same(gh.get(path), rule):
                done.append(f"{rule['name']}: already in place")
                continue
            gh.api("PUT", path, rule)
            done.append(f"{rule['name']}: updated")
        else:
            gh.api("POST", f"repos/{repository}/rulesets", rule)
            done.append(f"{rule['name']}: created")
    after = {r["name"]: r["id"] for r in gh.get(f"repos/{repository}/rulesets") or []}
    for rule in wanted(owner_type):
        if rule["name"] not in after:
            raise RuntimeError(f"{rule['name']} is missing after it was written")
    return done


def commands(repository: str, owner_type: str = "Organization") -> str:
    lines = []
    for rule in wanted(owner_type):
        lines.append(f"gh api -X POST repos/{repository}/rulesets --input - <<'JSON'\n"
                     f"{json.dumps(rule, indent=2)}\nJSON")
    return "\n\n".join(lines)


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="apply_rulesets", description=__doc__)
    parser.add_argument("repository", help="owner/name")
    parser.add_argument("--print", action="store_true", dest="print_only",
                        help="print the requests for an admin and change nothing")
    args = parser.parse_args(argv)
    if args.print_only:
        print(commands(args.repository))
        return 0
    try:
        for line in apply(gh or Gh(), args.repository):
            print(line)
    except (GhError, RuntimeError) as err:
        print(f"apply_rulesets: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
