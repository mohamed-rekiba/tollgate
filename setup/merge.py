"""Merge a ready change into main. You run it: the AI never approves its own work.

    python3 -m setup.merge list               the ready changes
    python3 -m setup.merge show <commit>      one change: its pass record, commits, and files
    python3 -m setup.merge approve <commit>   approve it, for tier 3 and 4
    python3 -m setup.merge merge <commit>     merge it into main

A ready change is a commit with a pass record that is not on main yet.
`approve` asks you to type `yes` in your terminal. It refuses to run when its input
is not a terminal, so a script or an AI cannot approve. The approval goes to
approvals/<commit>.json in the state folder. `merge` hands the commit to the
store, which merges with a merge commit and refuses a change with no pass
record, or a tier 3 or 4 change with no approval.
"""

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

from gate import state
from gate.store import Store, StoreError


class MergeError(RuntimeError):
    pass


def git(root, *args) -> tuple:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip()


def full(root, commit: str) -> str:
    code, out = git(root, "rev-parse", "-q", "--verify", f"{commit}^{{commit}}")
    if code:
        raise MergeError(f"no such commit: {commit}")
    return out


def ready(project: str, store) -> list:
    """[(commit, pass record)] for each commit with a pass record, not on main."""
    out = []
    for path in sorted(state.path(project, "passes").glob("*.json")):
        commit = path.stem
        if git(project, "merge-base", "--is-ancestor", commit, "main")[0] == 0:
            continue
        record = store.passed(commit)
        if record:
            out.append((commit, record))
    return out


def needs_approval(record: dict) -> bool:
    tier = record.get("tier", 4)
    return not isinstance(tier, int) or tier >= 3


def describe(project: str, commit: str, record: dict, store) -> list:
    branches = git(project, "branch", "--format=%(refname:short)", "--points-at", commit)[1]
    lines = [(f"{commit[:12]}  ticket {record.get('ticket', '?')}  tier {record.get('tier', '?')}"
              f"  score {record.get('score', '?')}  branch {branches.replace(chr(10), ', ') or '-'}")]
    if needs_approval(record):
        lines.append("  approved" if store.approvals(commit) else "  needs your approval")
    return lines


def show(project: str, commit: str, store) -> list:
    commit = full(project, commit)
    record = store.passed(commit)
    if record:
        lines = describe(project, commit, record, store)
    else:
        lines = [f"{commit[:12]}  a change made by hand: no pass record",
                 "  approved" if store.approvals(commit) else "  needs your approval"]
        record = {}
    for name, passed in sorted(record.get("checks", {}).items()):
        lines.append(f"  {'pass' if passed else 'FAIL'}  {name}")
    lines.append(git(project, "log", "--oneline", f"main..{commit}")[1])
    lines.append(git(project, "diff", "--stat", f"main...{commit}")[1])
    return lines


def approve(project: str, commit: str, store, approver: str = "") -> Path:
    """Write your approval of a commit. The caller has asked you to confirm it first."""
    commit = full(project, commit)
    record = store.passed(commit)
    if not record:
        # A change made by hand has no ticket, so the gate cannot pass it. Your approval
        # vouches for it. An AI ticket always needs the gate's pass.
        if git(project, "branch", "--contains", commit, "--list", "tg/*")[1]:
            raise MergeError(f"{commit[:12]} is on a ticket branch and has no pass record. "
                             "Only the gate passes a ticket.")
        record = {"ticket": "", "tier": 4}
    elif not needs_approval(record):
        raise MergeError(f"{commit[:12]} is tier {record.get('tier')}: it needs no approval")
    approver = approver or git(project, "config", "user.email")[1] or "you"
    at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = state.path(project, "approvals", f"{commit}.json")
    state.write_record(path, {"commit": commit, "ticket": record.get("ticket", ""),
                              "approver": approver, "at": at})
    return path


def confirm(project: str, commit: str, store, ask=None) -> None:
    """Show the change and ask you to type yes. Raise MergeError on anything else, and
    when stdin is not a terminal."""
    if not sys.stdin.isatty():
        raise MergeError("approve needs a terminal: run it yourself, in your own shell")
    print("\n".join(show(project, commit, store)))
    if (ask or input)("Type yes to approve this change: ").strip().lower() != "yes":
        raise MergeError("not approved")


def merge(project: str, commit: str, store) -> str:
    commit = full(project, commit)
    record = store.passed(commit)
    if not record:
        # A change made by hand, such as the rules a home syncs, merges on your approval.
        if not any(not a["ticket"] for a in store.approvals(commit)):
            raise MergeError(f"{commit[:12]} has no pass record and no approval. "
                             "A change made by hand needs your approval first.")
    elif needs_approval(record) and not store.approvals(commit):
        raise MergeError(f"{commit[:12]} is tier {record.get('tier')}: approve it first")
    return store.merge(commit)


def main(argv=None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="merge", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for name in ("show", "approve", "merge"):
        p = sub.add_parser(name)
        p.add_argument("commit")
    args = parser.parse_args(argv)
    project = str(Path(args.project).resolve())
    store = store or Store(project)
    try:
        if args.command == "list":
            found = ready(project, store)
            if not found:
                print("No change is ready to merge.")
            for commit, record in found:
                print("\n".join(describe(project, commit, record, store)))
        elif args.command == "show":
            print("\n".join(show(project, args.commit, store)))
        elif args.command == "approve":
            confirm(project, args.commit, store)
            print(f"approved: {approve(project, args.commit, store)}")
        else:
            print(f"merged: {merge(project, args.commit, store)}")
    except (MergeError, StoreError, state.RecordError, OSError, ValueError) as err:
        print(f"merge: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
