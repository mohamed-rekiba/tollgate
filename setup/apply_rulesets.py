"""Make the gate required on the main branch and lock the tags under tg/.

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


def wanted() -> list:
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
            {"type": "required_status_checks", "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [
                    {"context": "tollgate gate", "integration_id": GITHUB_ACTIONS_APP}]}},
        ],
        "bypass_actors": [],
    }
    # Only the freeze workflow, through GitHub Actions, may create these tags.
    # Nobody may move or delete them.
    tags = {
        "name": TAG_RULESET, "target": "tag", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["refs/tags/tg/**"], "exclude": []}},
        "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}],
        "bypass_actors": [{"actor_id": GITHUB_ACTIONS_APP, "actor_type": "Integration",
                           "bypass_mode": "always"}],
    }
    return [branch, tags]


def _same(have: dict, want: dict) -> bool:
    keys = ("target", "enforcement", "conditions", "rules")
    return all(have.get(k) == want[k] for k in keys)


def apply(gh, repository: str) -> list:
    """Create or update both rulesets. Return what it did for each."""
    existing = {r["name"]: r["id"] for r in gh.get(f"repos/{repository}/rulesets") or []}
    done = []
    for rule in wanted():
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
    for rule in wanted():
        if rule["name"] not in after:
            raise RuntimeError(f"{rule['name']} is missing after it was written")
    return done


def commands(repository: str) -> str:
    lines = []
    for rule in wanted():
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
