"""Check that each commit that reaches main passed the gate. Python 3, standard library only.

Tollgate copies this file into a project as .tollgate/checks/check_merge.py.
pre-commit runs it in two stages:

    python3 .tollgate/checks/check_merge.py merge   (pre-merge-commit)
    python3 .tollgate/checks/check_merge.py push    (pre-push)

A merge into main needs a pass record for the commit it merges, and a change of
tier 3 or 4 also needs an approval. A push to main needs the same for each merge
on main's first-parent line, and refuses a commit made on main itself. Commits
from before Tollgate was set up are not checked.

It reads the records from the state folder, which no role may write. The rule for its path is a copy of
gate/state.py, so this file runs with no Tollgate code. A test checks that the
copy agrees with gate/state.py.

It ends with 0 when the merge or push may go on, and 1 with one line for each
problem when it may not.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

MAIN = "main"
SETTINGS = ".tollgate/settings.json"
ZERO = "0" * 40


def git(root, *args):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip()


# The state folder: a copy of gate/state.py.

def state_root() -> Path:
    if os.environ.get("TOLLGATE_STATE"):
        return Path(os.environ["TOLLGATE_STATE"])
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "tollgate"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "tollgate"


def state_dir(project: str) -> Path:
    real = os.path.realpath(project)
    tag = hashlib.sha256(real.encode()).hexdigest()[:10]
    return state_root() / f"{Path(real).name}-{tag}"


def project_root(cwd=".") -> str:
    """The project folder. A git worktree of the project, such as a builder's copy,
    gets the project's own folder, so it reads the same state."""
    code, common = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if code == 0 and Path(common).name == ".git":
        return str(Path(common).parent)
    return git(cwd, "rev-parse", "--show-toplevel")[1] or os.path.abspath(cwd)


def read(path: Path):
    """The record at path, or None when it is missing or not a record."""
    try:
        record = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def check_start(root, folder: Path, record: dict, onto: str) -> list:
    """A ticket's pass record and its lock both name the commit the ticket started
    from. In a task that is the ready change before it, and the ticket's tier counts
    only its own files. So the lock must be there, be the lock that passed, name the
    same start as the record, and that start must already be on main (onto), or it
    would come in with no check of its own. Anything else fails closed."""
    ticket = record.get("ticket")
    if not ticket:
        return []
    path = folder / "locks" / f"{ticket}.json"
    lock = read(path)
    if lock is None:
        return [f"ticket {ticket} has no lock that can be read, so its start cannot be checked"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("lock_sha256"):
        return [f"ticket {ticket} was locked again after its pass record; it must pass again"]
    if "base_commit" not in record:
        return [(f"the pass record of ticket {ticket} was made by an older Tollgate, with no "
                 "start; the change must pass the gate again")]
    start = record.get("base_commit")
    if not isinstance(start, str) or not start or lock.get("base_commit") != start:
        return [f"the pass record of ticket {ticket} names no start, or not its lock's start"]
    if git(root, "merge-base", "--is-ancestor", start, onto)[0] != 0:
        return [(f"ticket {ticket} builds on {start[:12]}, which is not on {MAIN}; merge the "
                 "ticket before it first")]
    return []


def check_commit(root, commit: str, onto: str = f"refs/heads/{MAIN}") -> list:
    """The problems that stop commit from reaching main, merged onto the commit onto.
    None means it may."""
    folder = state_dir(project_root(root))
    record = read(folder / "passes" / f"{commit}.json")
    if not record or record.get("commit") != commit:
        # A change made by hand has no ticket: your approval vouches for it.
        approval = read(folder / "approvals" / f"{commit}.json")
        if approval and approval.get("commit") == commit and not approval.get("ticket"):
            return []
        return [(f"commit {commit[:12]} has no pass record, and no approval of a "
                 "change made by hand. Approve it with /tollgate:merge.")]
    tier = record.get("tier", 4)
    if not isinstance(tier, int) or tier >= 3:
        approval = read(folder / "approvals" / f"{commit}.json")
        if not approval or approval.get("commit") != commit:
            return [(f"commit {commit[:12]} is tier {tier} and has no approval. "
                     "Approve it with /tollgate:merge.")]
    return check_start(root, folder, record, onto)


def merge_heads(root) -> list:
    """The commits a merge in progress brings. In the pre-merge-commit hook git has
    not written MERGE_HEAD yet; it names each one in a GITHEAD_<commit> variable."""
    heads = sorted(k[len("GITHEAD_"):] for k in os.environ if k.startswith("GITHEAD_"))
    if heads:
        return heads
    path = git(root, "rev-parse", "--git-path", "MERGE_HEAD")[1]
    target = Path(root, path)
    return target.read_text().split() if path and target.exists() else []


def check_merge(root) -> list:
    """pre-merge-commit: a merge into main must bring only commits that passed."""
    code, branch = git(root, "symbolic-ref", "-q", "HEAD")
    if code != 0 or branch != f"refs/heads/{MAIN}":
        return []
    heads = merge_heads(root)
    if not heads:
        return ["a merge into main, but git names no commit that it merges"]
    return [p for head in heads for p in check_commit(root, head, "HEAD")]


def has_settings(root, commit: str) -> bool:
    return git(root, "cat-file", "-e", f"{commit}:{SETTINGS}")[0] == 0


def check_push(root, to_ref: str, from_ref: str = "", branch: str = "") -> list:
    """pre-push: each commit that reaches main on its first-parent line is a
    merge of a commit that passed."""
    if branch != f"refs/heads/{MAIN}" or not to_ref or to_ref == ZERO:
        return []
    span = [to_ref] if not from_ref or from_ref == ZERO else [f"{from_ref}..{to_ref}"]
    code, out = git(root, "rev-list", "--first-parent", "--parents", *span)
    if code != 0:
        return [f"cannot read the commits to push: {to_ref[:12]}"]
    problems = []
    for line in out.splitlines():
        commit, *parents = line.split()
        if not parents or not has_settings(root, parents[0]):
            continue  # from before Tollgate was set up, or the setup itself
        if len(parents) < 2:
            problems.append(f"commit {commit[:12]} was made on main. A change reaches main "
                            "only as a merge by /tollgate:merge.")
            continue
        problems += check_commit(root, parents[1], parents[0])
    return problems


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stage = argv[0] if argv else "merge"
    root = git(".", "rev-parse", "--show-toplevel")[1] or "."
    if stage == "push":
        env = os.environ
        problems = check_push(root, env.get("PRE_COMMIT_TO_REF", ""),
                              env.get("PRE_COMMIT_FROM_REF", ""),
                              env.get("PRE_COMMIT_REMOTE_BRANCH", ""))
    else:
        problems = check_merge(root)
    for line in problems:
        print(f"check_merge: {line}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
