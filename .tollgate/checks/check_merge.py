"""Check that each commit that reaches main passed the gate. Python 3, standard library only.

Tollgate copies this file into a project as .tollgate/checks/check_merge.py.
pre-commit runs it in two stages:

    python3 .tollgate/checks/check_merge.py merge   (pre-merge-commit)
    python3 .tollgate/checks/check_merge.py push    (pre-push)

A merge into main needs a verified pass record for the commit it merges, and a
change of tier 3 or 4 also needs a verified approval. A push to main needs the
same for each merge on main's first-parent line, and refuses a commit made on
main itself. Commits from before Tollgate was set up are not checked.

It verifies each signature with `ssh-keygen -Y verify`, against the settings on
main, never the settings of the change: a pass record against `signers`, the
machine keys; an approval against `owners`, the keys of the people who approve.
So the machine key can never approve.

It reads the records from the state folder. The rule for its path is a copy of
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
import tempfile
from pathlib import Path

MAIN = "main"
SETTINGS = ".tollgate/settings.json"
IDENTITY = "tollgate"
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


def key_dir() -> Path:
    if os.environ.get("TOLLGATE_KEYS"):
        return Path(os.environ["TOLLGATE_KEYS"])
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
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


# Signatures: a copy of the verify step of gate/sign.py.

def verify(data: bytes, signature: bytes, namespace: str, signers: list) -> bool:
    if not signers or not signature:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        allowed = Path(tmp, "allowed")
        allowed.write_text("".join(f'{IDENTITY} namespaces="{namespace}" {k.strip()}\n'
                                   for k in signers))
        sig = Path(tmp, "sig")
        sig.write_bytes(signature)
        proc = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", IDENTITY,
                               "-n", namespace, "-s", str(sig)],
                              input=data, capture_output=True, check=False)
        return proc.returncode == 0


def read(path: Path, namespace: str, signers: list):
    """The record at path when its signature verifies, else None."""
    sig = Path(f"{path}.sig")
    if not path.exists() or not sig.exists():
        return None
    data = path.read_bytes()
    if not verify(data, sig.read_bytes(), namespace, signers):
        return None
    try:
        return json.loads(data)
    except ValueError:
        return None


def keys_on_main(root, name: str) -> list:
    """A key list of the settings on main: signers or owners."""
    code, text = git(root, "show", f"refs/heads/{MAIN}:{SETTINGS}")
    if code != 0:
        return []
    try:
        return list(json.loads(text).get(name, []))
    except (ValueError, AttributeError):
        return []


def check_start(root, folder: Path, record: dict, signers: list, onto: str) -> list:
    """A ticket's lock names the commit the ticket started from. In a task that is the
    ready change before it, and the ticket's tier counts only its own files. So the
    start must already be on main (onto), or it would come in with no check of its own."""
    ticket = record.get("ticket")
    if not ticket:
        return []
    path = folder / "locks" / f"{ticket}.json"
    if not path.exists():
        return []
    lock = read(path, "tollgate-lock", signers)
    if lock is None or hashlib.sha256(path.read_bytes()).hexdigest() != record.get("lock_sha256"):
        return []   # not the lock this record passed with: the store refuses that merge
    start = str(lock.get("base_commit") or "")
    if not start or git(root, "merge-base", "--is-ancestor", start, onto)[0] != 0:
        return [(f"ticket {ticket} builds on {start[:12]}, which is not on {MAIN}; merge the "
                 "ticket before it first")]
    return []


def check_commit(root, commit: str, onto: str = f"refs/heads/{MAIN}") -> list:
    """The problems that stop commit from reaching main, merged onto the commit onto.
    None means it may."""
    signers = keys_on_main(root, "signers")
    if not signers:
        return [f"{MAIN} has no signers in {SETTINGS}. Run /tollgate:init."]
    folder = state_dir(project_root(root))
    record = read(folder / "passes" / f"{commit}.json", "tollgate-pass", signers)
    if not record or record.get("commit") != commit:
        # A change made by hand has no ticket: an owner's approval vouches for it.
        owners = keys_on_main(root, "owners")
        approval = read(folder / "approvals" / f"{commit}.json", "tollgate-approval", owners)
        if approval and approval.get("commit") == commit and not approval.get("ticket"):
            return []
        return [(f"commit {commit[:12]} has no verified pass record, and no approval of a "
                 "change made by hand. Approve it with /tollgate:merge.")]
    tier = record.get("tier", 4)
    if not isinstance(tier, int) or tier >= 3:
        owners = keys_on_main(root, "owners")
        approval = read(folder / "approvals" / f"{commit}.json", "tollgate-approval", owners)
        if not approval or approval.get("commit") != commit:
            return [(f"commit {commit[:12]} is tier {tier} and has no verified approval. "
                     "Approve it with /tollgate:merge.")]
    return check_start(root, folder, record, signers, onto)


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
