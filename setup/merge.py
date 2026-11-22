"""Merge a ready change into main. You run it: the AI never approves its own work.

    python3 -m setup.merge list               the ready changes
    python3 -m setup.merge show <commit>      one change: its pass record, commits, and files
    python3 -m setup.merge approve <commit>   sign your approval, for tier 3 and 4
    python3 -m setup.merge merge <commit>     merge it into main

A ready change is a commit with a verified pass record that is not on main yet.
`approve` asks ssh-keygen to sign the approval with your SSH key:

    ssh-keygen -Y sign -n tollgate-approval -f ~/.ssh/<key> approvals/<commit>.json

ssh-keygen asks for the key's passphrase in your terminal. The approval goes to
approvals/<commit>.json in the state folder. `merge` hands the commit to the
store, which merges with a merge commit and refuses a change with no pass
record, or a tier 3 or 4 change with no approval.
"""

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

from gate import settings as st
from gate import sign, state
from gate.store import Store, StoreError

NAMESPACE = "tollgate-approval"
KEYS = ("id_ed25519", "id_ecdsa", "id_ed25519_sk", "id_rsa")


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
    """[(commit, pass record)] for each commit with a verified pass, not on main."""
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


def private_key(path: str | None) -> Path:
    if path:
        key = Path(path).expanduser()
        if key.exists():
            return key
        raise MergeError(f"no key at {key}")
    for name in KEYS:
        key = Path.home() / ".ssh" / name
        if key.exists():
            return key
    raise MergeError("no SSH key in ~/.ssh/. Name one with --key.")


def owners(project: str) -> list:
    """The keys in `owners` in the settings on main: the people who approve."""
    code, text = git(project, "show", f"main:{st.PATH}")
    if code:
        raise MergeError(f"main has no {st.PATH}. Run /tollgate:init.")
    return list(json.loads(text).get("owners", []))


def approve(project: str, commit: str, store, key: str | None = None, approver: str = "") -> Path:
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
    key_path = private_key(key)
    if key_path.resolve() == sign.machine_key().resolve():
        raise MergeError("that is the machine key. Sign with your own SSH key.")
    approver = approver or git(project, "config", "user.email")[1] or key_path.name
    at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    path = state.path(project, "approvals", f"{commit}.json")
    data = state.dumps({"commit": commit, "ticket": record.get("ticket", ""),
                        "approver": approver, "at": at})
    path.write_bytes(data)
    Path(f"{path}.sig").unlink(missing_ok=True)
    # Not captured, so ssh-keygen asks for the passphrase in your terminal.
    done = subprocess.run(["ssh-keygen", "-Y", "sign", "-q", "-n", NAMESPACE, "-f",
                           str(key_path), str(path)], check=False)
    sig = Path(f"{path}.sig")
    if done.returncode or not sig.exists():
        path.unlink(missing_ok=True)
        raise MergeError("ssh-keygen did not sign the approval")
    if not sign.verify(data, sig.read_bytes(), NAMESPACE, owners(project)):
        path.unlink()
        sig.unlink()
        raise MergeError(f"{key_path} is not in owners on main. Add its public key with "
                         "/tollgate:init --owner-key.")
    return path


def merge(project: str, commit: str, store) -> str:
    commit = full(project, commit)
    record = store.passed(commit)
    if not record:
        # A change made by hand, such as the rules a home syncs, merges on your approval.
        if not any(not a["ticket"] for a in store.approvals(commit)):
            raise MergeError(f"{commit[:12]} has no verified pass record and no approval. "
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
        if name == "approve":
            p.add_argument("--key", help="your private SSH key; the default is in ~/.ssh/")
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
            print(f"approved: {approve(project, args.commit, store, args.key)}")
        else:
            print(f"merged: {merge(project, args.commit, store)}")
    except (MergeError, StoreError, sign.SignError, OSError, ValueError) as err:
        print(f"merge: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
