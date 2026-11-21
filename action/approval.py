"""Did a person approve this commit of a pull request? The workflow asks this
before the tests run: a change made by hand and approved runs its tests with
its own harness.

The rule is `gate.approved`, the same one the gate applies later. The
approvers come from the settings in the main branch's checkout, read the same
way the gate reads them. It prints `true` or `false`. Any error ends with 1 and
prints nothing on standard output, so the workflow treats it as not approved.
"""

import argparse
import sys

from action import gate
from action import settings as st


def is_approved(server, settings: dict, pr: int, sha: str) -> bool:
    """True when a person the settings accept approved commit `sha` of pull request `pr`."""
    facts = gate.Facts(settings=settings, branch="", head_sha=sha, changes={}, results=None,
                       pr_author=server.pull(pr)["author"], approvals=server.approvals(pr))
    return gate.approved(facts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate approval", description=__doc__)
    parser.add_argument("--repo", required=True, help="a checkout of the main branch")
    parser.add_argument("--repository", required=True, help="owner/name")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--sha", required=True, help="the commit the tests will run on")
    args = parser.parse_args(argv)
    try:
        from action.server import Server
        settings = st.load_from_ref(args.repo, "HEAD")
        answer = is_approved(Server(args.repository), settings, args.pr, args.sha)
    except Exception as err:  # noqa: BLE001 - any failure means not approved
        print(f"approval: {err}", file=sys.stderr)
        return 1
    print("true" if answer else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
