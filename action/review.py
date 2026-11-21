"""The review on the server, for tier 3 and 4. It posts the check "tollgate review".

It reads the change as text and runs none of it. Tier 1 and 2 pass at once.
For tier 3 and 4 it runs the reviewer with the change lens and the security lens,
with the model key from the secret ANTHROPIC_API_KEY. Without a key it fails, so
the pull request waits.
"""

import argparse
import json
import os
import sys
import tempfile

from action import gate, tiers
from action import settings as st
from action.gitio import changed_files, git, show_bytes

REVIEW_CHECK = gate.REVIEW_CHECK
LENSES_BY_TIER = {3: ("change", "security"), 4: ("change", "security")}


def tier_of(repo, base, head, branch) -> tuple:
    settings = st.load_from_ref(repo, base)
    changes = changed_files(repo, base, head)
    ticket = gate.ticket_of(branch)
    freeze = gate._freeze(repo, ticket) if ticket else None
    frozen = set(freeze.manifest.get("files", {})) if freeze else set()
    level, reason = tiers.tier(settings, changes, frozen)
    return level, reason, settings, freeze


def review(repo, base, head, branch, run_role=None, key=None) -> tuple:
    """Return (passed, title, text)."""
    level, reason, settings, freeze = tier_of(repo, base, head, branch)
    if level < 3:
        return True, f"Not needed for tier {level}.", reason
    key = os.environ.get("ANTHROPIC_API_KEY") if key is None else key
    if not key and run_role is None:
        return False, f"Tier {level} needs the review, and there is no model key.", (
            "Add the repository secret ANTHROPIC_API_KEY, then comment `tollgate check`.")
    ticket = ""
    if freeze:
        data = show_bytes(repo, freeze.tag_commit, f".tollgate/tickets/{freeze.manifest['ticket']}"
                          "/ticket.md")
        ticket = data.decode() if data else ""
    diff = git(repo, "diff", f"{base}...{head}")[:120000]
    if run_role is None:
        from driver import roles

        def run_role(lens, inputs):
            with tempfile.TemporaryDirectory() as empty:
                return roles.run(settings["ai"]["reviewer"], "reviewer", inputs, empty, 15,
                                 lens=lens).data
    findings = []
    for lens in LENSES_BY_TIER[level]:
        data = run_role(lens, {"ticket": ticket, "diff": diff, "tier": level})
        for f in data.get("findings", []):
            findings.append({**f, "lens": lens})
        if data.get("verdict") == "fail" and not any(f.get("level") == "blocking"
                                                     for f in data.get("findings", [])):
            findings.append({"lens": lens, "level": "blocking", "text": "the reviewer failed it"})
    blocking = [f for f in findings if f.get("level") == "blocking"]
    lines = [f"- {f.get('level')} ({f['lens']}): {f.get('text', '')}"
             + (f" `{f['file']}:{f.get('line', '')}`" if f.get("file") else "") for f in findings]
    title = (f"Passed. Tier {level}." if not blocking
             else f"Failed: {len(blocking)} blocking finding(s). Tier {level}.")
    return not blocking, title, "\n".join(lines) or "No findings."


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate review", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--repository")
    parser.add_argument("--post", metavar="SHA")
    parser.add_argument("--tier-out", help="write only the tier to this file and stop")
    args = parser.parse_args(argv)
    try:
        if args.tier_out:
            level = tier_of(args.repo, args.base, args.head, args.branch)[0]
            with open(args.tier_out, "w") as f:
                f.write(str(level))
            print(level)
            return 0
        passed, title, text = review(args.repo, args.base, args.head, args.branch)
    except Exception as err:  # noqa: BLE001 - any failure posts a failing check
        passed, title, text = False, "The review could not run.", str(err)
    print(json.dumps({"passed": passed, "title": title}))
    print(text)
    if args.post and args.repository:
        from action.server import Server
        Server(args.repository).post_check(args.post, REVIEW_CHECK, passed, title, text)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
