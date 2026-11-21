"""Build the manifest for a freeze and write the message of the freeze tag.

The freeze workflow runs this in a job that never runs the change's code. It
reads the test report that an earlier job produced.
"""

import argparse
import re
import sys

from action import junit, tickets
from action import manifest as mf
from action import settings as st
from action.checks import Results
from action.gitio import git, show_bytes
from action.paths import matches

TICKET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_FREEZES = 2


def next_number(repo, ticket_id: str) -> int:
    prefix = f"refs/tags/tg/freeze/{ticket_id}/"
    refs = git(repo, "for-each-ref", "--format=%(refname)", prefix).split()
    numbers = [int(r[len(prefix):]) for r in refs if r[len(prefix):].isdigit()]
    return max(numbers, default=0) + 1


def message(repo, ticket_id: str, commit: str, results: str, run_id: str,
            base: str = "origin/main") -> tuple:
    """Return (tag name, tag message). Raise FreezeError when the ticket cannot be frozen."""
    if not TICKET_ID.match(ticket_id):
        raise mf.FreezeError(f"not a valid ticket id: {ticket_id!r}")
    number = next_number(repo, ticket_id)
    if number > MAX_FREEZES:
        raise mf.FreezeError(f"ticket {ticket_id} already has {MAX_FREEZES} freezes")
    data = show_bytes(repo, commit, mf.ticket_path(ticket_id))
    if data is None:
        raise mf.FreezeError(f"{mf.ticket_path(ticket_id)} is not in commit {commit}")
    ticket = tickets.parse(data.decode())
    if ticket.id != ticket_id:
        raise mf.FreezeError(f"the ticket file names {ticket.id}, not {ticket_id}")
    settings = st.load_from_ref(repo, base)
    guarded = settings["harness"] + settings["tiers"]["3"] + settings["tiers"]["4"]
    for path in ticket.tests:
        if matches(path, guarded):
            raise mf.FreezeError(f"{path} is harness or a tier 3 or 4 path, so it cannot be locked")
    with open(results) as f:
        tests = Results.from_json(f.read()).tests
    found = {i: junit.TestResult(i, r["status"], r.get("file", "")) for i, r in tests.items()}
    manifest = mf.build(repo, commit, ticket, found)
    manifest["run_id"] = int(run_id)
    manifest["number"] = number
    name = f"tg/freeze/{ticket_id}/{number}"
    return name, f"Freeze {number} of ticket {ticket_id}\n\n{mf.dumps(manifest)}\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate freeze", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--results", required=True, help="results file from action.checks")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True, help="file for the tag message")
    parser.add_argument("--name-out", required=True, help="file for the tag name")
    parser.add_argument("--base", default="origin/main", help="read the settings from here")
    args = parser.parse_args(argv)
    try:
        name, text = message(args.repo, args.ticket, args.commit, args.results, args.run_id,
                             args.base)
    except Exception as err:  # noqa: BLE001 - any failure refuses the freeze
        print(f"the ticket cannot be frozen: {err}", file=sys.stderr)
        return 1
    with open(args.out, "w") as f:
        f.write(text)
    with open(args.name_out, "w") as f:
        f.write(name)
    print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
