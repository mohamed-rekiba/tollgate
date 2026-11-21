"""The store: the part of Tollgate that keeps its state on your machine.

The driver, the gate, and the skills reach the state folder only through this
class. Every method names one step. The project is a git repository on your
machine: the store reads its `main` branch and the branches `tg/<ticket>` and
`tg-plan/<task>`.

Every record that the store trusts is signed. It verifies a record with the
`signers` from the settings on main, never from the change.

UNFINISHED: `freeze` runs the tests on this machine, in a temporary clone. Running
them in the builder's isolation is the driver stream's work.
"""

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gate import checks, plantag, prepare, sign, state, tickets
from gate import freeze as fz
from gate import manifest as mf
from gate import plan as pl
from gate import settings as st
from gate.gitio import GitError, commit_of, fingerprint, git, show_bytes, worktree_of

MAIN = "main"
PASS_KEYS = {"commit", "ticket", "tier", "lock_sha256", "checks", "score", "at"}
APPROVAL_KEYS = {"commit", "ticket", "approver", "at"}
DECIDE_PREFIX = "tollgate decide "


class StoreError(RuntimeError):
    """A step of the store failed. The message says why."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, project: str):
        self.project = str(project)
        self.dir = state.state_dir(self.project)

    # Helpers.

    def _main(self) -> str:
        commit = commit_of(self.project, f"refs/heads/{MAIN}")
        if not commit:
            raise StoreError(f"the project has no branch {MAIN}")
        return commit

    def _settings(self) -> dict:
        try:
            return st.load_from_ref(self.project, f"refs/heads/{MAIN}")
        except st.SettingsError as err:
            raise StoreError(f"the settings on {MAIN} cannot be read: {err}") from None

    def _signers(self) -> list:
        return self._settings()["signers"]

    def _check_key(self) -> None:
        """Refuse when main does not list this machine's key, since nothing could verify
        a record it signs."""
        key = sign.ensure_key()
        if key.split()[:2] not in [s.split()[:2] for s in self._signers()]:
            raise StoreError(f"this machine's key is not in signers on {MAIN}: {key}")

    def _sign(self, path: Path, record: dict, namespace: str) -> None:
        self._check_key()
        sign.write(path, record, namespace)

    def _read(self, path: Path, namespace: str, keys: set, commit: str,
              signers: list | None = None) -> dict | None:
        """The verified record at path, or None when it is missing, does not verify,
        has other keys, or names another commit."""
        try:
            found = sign.read(path, namespace, self._signers() if signers is None else signers)
        except sign.SignError:
            return None
        if set(found) != keys or found.get("commit") != commit:
            return None
        return found

    @staticmethod
    def _commit_name(commit: str) -> str:
        if not commit or not all(c in "0123456789abcdef" for c in commit) or len(commit) < 40:
            raise StoreError(f"not a full commit id: {commit!r}")
        return commit

    # Locks.

    def freeze(self, ticket: str) -> str:
        """Run the ticket's tests in a clean copy with main's harness; none may pass.
        Write and sign locks/<ticket>.json. Return the lock's path."""
        self._check_key()
        try:
            fz.check_id(ticket)
            number = fz.next_number(self.project, ticket)
            if number > fz.MAX_FREEZES:
                raise mf.FreezeError(f"ticket {ticket} already has {fz.MAX_FREEZES} freezes")
            commit = commit_of(self.project, f"refs/heads/tg/{ticket}")
            if not commit:
                raise mf.FreezeError(f"the project has no branch tg/{ticket}")
            base = self._main()
            settings = self._settings()
            ticket_file = self._approved_ticket(ticket, commit, base)
            with tempfile.TemporaryDirectory() as d:
                git(d, "clone", "-q", "--no-checkout", self.project, ".")
                git(d, "checkout", "-q", "--detach", commit)
                prepare.restore(d, base, *ticket_file)
                for command in settings["setup"]:
                    done = subprocess.run(command, shell=True, cwd=d, capture_output=True,
                                          text=True, check=False, env=checks.project_env())
                    if done.returncode:
                        raise mf.FreezeError(f"the setup command failed: {command}")
                # UNFINISHED: the tests run here, not in the builder's isolation.
                results = checks.run(settings, d, ["tests"])
                lock = fz.record(d, ticket, commit, base, settings, results.tests, number)
        except (mf.FreezeError, pl.PlanError, st.SettingsError, sign.SignError, GitError,
                ValueError) as err:
            raise StoreError(f"the ticket cannot be frozen: {err}") from None
        lock["at"] = _now()
        self._check_key()
        path = fz.lock_path(self.project, ticket)
        if number > 1:
            old = fz.replaced_path(self.project, ticket)
            path.replace(old)
            Path(f"{path}.sig").replace(f"{old}.sig")
        self._sign(path, lock, fz.NAMESPACE)
        return str(path)

    def _approved_ticket(self, ticket: str, commit: str, base: str) -> tuple:
        """Return (commit, {"files": {path: fingerprint}}) of the approved ticket file, for
        prepare.restore. The approved file is the one in the plan lock, else main's. Raise
        FreezeError when the ticket's commit holds another text."""
        path = mf.ticket_path(ticket)
        committed = show_bytes(self.project, commit, path)
        if committed is None:
            raise mf.FreezeError(f"{path} is not in commit {commit}")
        plan_id = tickets.parse(committed.decode()).plan
        source, approved = None, None
        if plan_id and pl.ID.match(plan_id) and state.path(self.project, "plans",
                                                          f"{plan_id}.json").exists():
            locked = sign.read(state.path(self.project, "plans", f"{plan_id}.json"),
                               "tollgate-plan", self._signers())
            if path in locked["files"]:
                source, approved = locked["commit"], locked["files"][path]
        if approved is None:
            on_main = show_bytes(self.project, base, path)
            if on_main is not None:
                source, approved = base, fingerprint(on_main)
        if approved is not None and fingerprint(committed) != approved:
            raise mf.FreezeError(f"{path} differs from the approved ticket")
        return (source, {"files": {path: approved}}) if source else (None, None)

    def lock_plan(self, task: str) -> str:
        """Sign the approved plan of a task into plans/<task>.json. Return its path."""
        if not pl.ID.match(task or ""):
            raise StoreError(f"not a valid task id: {task!r}")
        path = state.path(self.project, "plans", f"{task}.json")
        if path.exists():
            raise StoreError(f"the plan of task {task} is already locked")
        commit = commit_of(self.project, f"refs/heads/tg-plan/{task}")
        if not commit:
            raise StoreError(f"the project has no branch tg-plan/{task}")
        try:
            found = plantag.record(self.project, task, commit)
        except pl.PlanError as err:
            raise StoreError(f"the plan cannot be locked: {err}") from None
        found["at"] = _now()
        self._sign(path, found, "tollgate-plan")
        return str(path)

    # Questions for you.

    def _question_path(self, n: int, closed: bool = False) -> Path:
        if not isinstance(n, int) or n < 1:
            raise StoreError(f"not a question number: {n!r}")
        return state.path(self.project, "questions", f"{n}.closed.json" if closed else f"{n}.json")

    def ask(self, title: str, body: str, options: list | None = None) -> int:
        """Write questions/<n>.json. Return n."""
        folder = state.path(self.project, "questions")
        numbers = [int(p.name.split(".")[0]) for p in folder.glob("*.json")
                   if p.name.split(".")[0].isdigit()]
        n = max(numbers, default=0) + 1
        record = {"n": n, "title": title, "body": body, "options": list(options or []),
                  "answer": None}
        while True:
            try:
                fd = os.open(self._question_path(n), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                break
            except FileExistsError:
                n += 1
                record["n"] = n
        with os.fdopen(fd, "wb") as f:
            f.write(state.dumps(record))
        return n

    def question(self, n: int) -> dict | None:
        """Question n, open or closed, or None when there is none."""
        for closed in (False, True):
            path = self._question_path(n, closed)
            if path.exists():
                return json.loads(path.read_text())
        return None

    def answer(self, n: int, body: str) -> None:
        """Record your answer to question n. The first line is the decision, then a hint:
        `approve keep the retries short`. A leading `tollgate decide` is allowed."""
        path = self._question_path(n)
        if not path.exists():
            raise StoreError(f"question {n} is not open")
        question = json.loads(path.read_text())
        first = (body or "").strip().splitlines()[:1]
        line = first[0].strip() if first else ""
        line = line[len(DECIDE_PREFIX):].strip() if line.startswith(DECIDE_PREFIX) else line
        decision, _, hint = line.partition(" ")
        if not decision:
            raise StoreError("the answer has no decision on its first line")
        if question["options"] and decision not in question["options"]:
            raise StoreError(f"{decision} is not one of: {', '.join(question['options'])}")
        question["answer"] = {"decision": decision, "hint": hint.strip(), "at": _now()}
        path.write_bytes(state.dumps(question))

    def open_questions(self) -> dict:
        """Return {n: question} for each question with no answer."""
        found = {}
        for path in state.path(self.project, "questions").glob("*.json"):
            if path.stem.isdigit():
                question = json.loads(path.read_text())
                if question["answer"] is None:
                    found[int(path.stem)] = question
        return dict(sorted(found.items()))

    def close_question(self, n: int) -> None:
        """Move question n to questions/<n>.closed.json. It keeps its answer."""
        path = self._question_path(n)
        if not path.exists():
            raise StoreError(f"question {n} is not open")
        path.replace(self._question_path(n, closed=True))

    # Ready changes, passes, approvals, merges.

    def _ready_path(self, ticket: str) -> Path:
        fz.check_id(ticket)
        folder = state.path(self.project, "passes", "ready")
        folder.mkdir(exist_ok=True)
        return folder / f"{ticket}.json"

    def ready(self, branch: str, ticket: str) -> None:
        """Mark a branch as a ready change: it passed the gate and waits to merge.
        Refuse when the branch's last commit has no verified pass record for the ticket."""
        try:
            path = self._ready_path(ticket)
        except mf.FreezeError as err:
            raise StoreError(str(err)) from None
        commit = commit_of(self.project, f"refs/heads/{branch}")
        if not commit:
            raise StoreError(f"the project has no branch {branch}")
        found = self.passed(commit)
        if not found or found["ticket"] != ticket:
            raise StoreError(f"{branch} at {commit[:12]} has no pass record for {ticket}")
        self._sign(path, {"branch": branch, "ticket": ticket, "commit": commit, "at": _now()},
                   "tollgate-pass")

    def record_pass(self, commit: str, record: dict) -> None:
        """Write and sign passes/<commit>.json."""
        self._commit_name(commit)
        record = dict(record)
        record.setdefault("at", _now())
        if set(record) != PASS_KEYS:
            raise StoreError(f"a pass record has the keys {', '.join(sorted(PASS_KEYS))}")
        if record["commit"] != commit:
            raise StoreError(f"the record names {record['commit']}, not {commit}")
        if record["tier"] not in (1, 2, 3, 4):
            raise StoreError(f"not a tier: {record['tier']!r}")
        self._sign(state.path(self.project, "passes", f"{commit}.json"), record, "tollgate-pass")

    def passed(self, commit: str) -> dict | None:
        """The verified pass record of a commit, or None."""
        self._commit_name(commit)
        return self._read(state.path(self.project, "passes", f"{commit}.json"),
                          "tollgate-pass", PASS_KEYS, commit)

    def approvals(self, commit: str) -> list:
        """The verified approvals of a commit."""
        self._commit_name(commit)
        found = self._read(state.path(self.project, "approvals", f"{commit}.json"),
                           "tollgate-approval", APPROVAL_KEYS, commit,
                           self._settings()["owners"])
        return [found] if found else []

    def merge(self, commit: str) -> str:
        """Merge a ready change into main with a merge commit (--no-ff). Refuse without
        a valid pass record, and for tier 3 and 4 without an approval. Return the merge commit."""
        full = commit_of(self.project, commit or "")
        if not full:
            raise StoreError(f"the project has no commit {commit!r}")
        found = self.passed(full)
        if not found:
            raise StoreError(f"{full[:12]} has no verified pass record")
        tier = found["tier"]
        if tier in (3, 4) and not any(a["ticket"] == found["ticket"] for a in self.approvals(full)):
            raise StoreError(f"{full[:12]} is tier {tier}, so it needs your signed approval")
        if found["ticket"] and found["lock_sha256"] != fz.lock_sha256(self.project, found["ticket"]):
            raise StoreError(f"the pass record of {full[:12]} is not for the current lock of "
                             f"{found['ticket']}")
        folder = worktree_of(self.project, MAIN)
        if not folder:
            raise StoreError(f"no worktree of the project has {MAIN} checked out")
        if git(folder, "status", "--porcelain", "--untracked-files=no").strip():
            raise StoreError(f"the {MAIN} worktree has changes; commit or stash them first")
        if subprocess.run(["git", "-C", folder, "merge-base", "--is-ancestor", full, MAIN],
                          capture_output=True, check=False).returncode == 0:
            raise StoreError(f"{full[:12]} is already in {MAIN}")
        name = found["ticket"] or "change"
        try:
            git(folder, "merge", "-q", "--no-ff", "--no-edit", "-m",
                f"merge({name}): {full[:12]} passed the gate at tier {tier}", full)
        except GitError as err:
            subprocess.run(["git", "-C", folder, "merge", "--abort"], capture_output=True,
                           check=False)
            raise StoreError(f"the merge failed: {err}") from None
        for path in state.path(self.project, "passes", "ready").glob("*.json"):
            if json.loads(path.read_text()).get("commit") == full:
                path.unlink()
                Path(f"{path}.sig").unlink(missing_ok=True)
        return git(folder, "rev-parse", "HEAD").strip()
