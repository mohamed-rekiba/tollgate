"""The driver: build one ticket, and stop when a stop rule says so.

The task, or a roadmap, starts it for each ticket. It runs on your machine and
calls no outside service. The steps:

1. The test writer writes the locked tests in the builder's copy, and a reviewer
   checks them through the test fit lens.
2. The driver fetches them from the copy into the project's branch tg/<ticket>,
   and the store freezes them: it writes and signs the lock.
3. Each try starts from the best try so far. The builder builds, the checks run,
   and the gate judges. A reviewer scores the checklist items that have no test.
4. A try that passes gets a signed pass record. The driver fetches it into the
   project and marks it as a ready change. With auto_merge on, the store merges
   tier 1 and 2. You merge tier 3 and 4.
5. Before each try, driver/stop.py says go on or stop. A stop goes to the advisor.

All run state lives in the state folder: the copy in builders/<ticket>/, the log
in logs/<ticket>.jsonl, the run lock in run/. A driver that starts again reads
the log and repeats no finished step.

Exit codes: 0 the ticket is a ready change or merged, 3 the ticket waits for the
advisor or is parked, 4 another driver holds the ticket, 1 an error.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from driver import advisor, history, roles, stop
from driver.log import Log, read
from gate import checks, prepare, state, tickets
from gate import gate as gatelib
from gate import manifest as mf
from gate import review as reviewlib
from gate import settings as st
from gate.store import Store, StoreError
from gate.tickets import item_of_test

MAX_REJECTIONS = 2
MAX_AI_DECISIONS = 2
BASE = "main"


class Busy(RuntimeError):
    pass


class Stop(Exception):
    """A stop rule fired. The reason goes to the advisor."""


class Parked(Exception):
    pass


# The run lock of a ticket or a task.

class TicketLock:
    def __init__(self, path):
        self.path = str(path)

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if _alive(_pid_in(self.path)):
                    raise Busy(f"another driver holds {self.path}") from None
                os.unlink(self.path)  # stale: its process is gone
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self
        raise Busy(f"could not take {self.path}")

    def release(self):
        if _pid_in(self.path) == os.getpid():
            os.unlink(self.path)


def run_lock(project: str, name: str) -> TicketLock:
    return TicketLock(state.path(project, "run", f"{name}.lock"))


def _pid_in(path) -> int:
    try:
        return int(Path(path).read_text().strip() or 0)
    except (OSError, ValueError):
        return 0


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# The score.

def line_exists(workdir: str, file: str, line) -> bool:
    try:
        path = Path(workdir, file).resolve()
        if not path.is_relative_to(Path(workdir).resolve()):
            return False
        return isinstance(line, int) and 1 <= line <= len(path.read_text().splitlines())
    except (OSError, UnicodeDecodeError, TypeError):
        return False


def score(ticket, test_status: dict, reviewed: list, workdir: str) -> tuple:
    """Return (score, {item id: passed}).

    An item with tests passes when all its tests pass. Any other item passes when
    the reviewer named a file and a line that exists.
    """
    by_item = {}
    for test_id, status in test_status.items():
        item = item_of_test(test_id)
        if item:
            by_item.setdefault(item, []).append(status == "passed")
    claims = {r.get("item"): r for r in reviewed if isinstance(r, dict)}
    passed = {}
    for item in ticket.items:
        if item.id in by_item:
            passed[item.id] = all(by_item[item.id])
        else:
            c = claims.get(item.id) or {}
            passed[item.id] = bool(c.get("passed")) and line_exists(workdir, c.get("file", ""),
                                                                    c.get("line"))
    value = round(100 * sum(passed.values()) / len(ticket.items)) if ticket.items else 0
    return value, passed


# Git.

def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def fetch_branch(project: str, copy: str, branch: str) -> None:
    """Fetch a branch of the copy into the project, under the same name."""
    git(project, "fetch", "-q", os.path.realpath(copy), f"+refs/heads/{branch}:refs/heads/{branch}")


def task_cost(logs_dir, task: str) -> float:
    total = 0.0
    for path in Path(logs_dir).glob("*.jsonl"):
        total += history.cost([e for e in read(str(path)) if e.get("task") == task])
    return round(total, 4)


class Driver:
    """gate_api and review_api default to gate.gate and gate.review. Tests pass fakes."""

    def __init__(self, project: str, ticket_id: str, store=None, ticket_text: str | None = None,
                 gate_api=None, review_api=None):
        self.project = os.path.abspath(project)
        self.ticket_id = ticket_id
        self.store = store or Store(self.project)
        self.gate = gate_api or gatelib
        self.review = review_api or reviewlib
        self.base = BASE
        self.branch = f"tg/{ticket_id}"
        self.logs = state.path(self.project, "logs")
        self.log_path = str(self.logs / f"{ticket_id}.jsonl")
        self.ticket_text = ticket_text or Path(self.project, mf.ticket_path(ticket_id)).read_text()
        self.ticket = tickets.parse(self.ticket_text)

    # Helpers.

    def role(self, name, inputs, lens=None, command=None):
        s = self.settings
        command = command or (s["ai"]["reviewer"] if name == "reviewer" else s["ai"]["builder"])
        return roles.run(command, name, inputs, self.copy, s["stop"]["attempt_minutes"], lens,
                         s["isolation"], s["container_image"], self.project)

    def lock(self) -> dict | None:
        """The ticket's lock as the store wrote it. The gate verifies its signature;
        the driver reads it only to put back the locked files and to score."""
        import json
        path = state.path(self.project, "locks", f"{self.ticket_id}.json")
        return json.loads(path.read_text()) if path.exists() else None

    def checks(self, only=None):
        lock = self.lock()
        prepare.restore(self.copy, self.base, lock["commit"] if lock else None,
                        lock["manifest"] if lock else None)
        try:
            for command in self.settings["setup"]:
                subprocess.run(command, shell=True, cwd=self.copy, check=False,
                               capture_output=True)
            return checks.run(self.settings, self.copy, only)
        finally:
            git(self.copy, "reset", "-q", "--hard", "HEAD")
            git(self.copy, "clean", "-q", "-fd")

    def commit(self, message) -> str:
        git(self.copy, "add", "-A")
        git(self.copy, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.copy, "rev-parse", "HEAD")

    def stop_check(self):
        """Raise Stop or Parked when a stop rule fires."""
        verdict = stop.check(read(self.log_path), self.settings,
                             task_cost(self.logs, self.ticket.plan) if self.ticket.plan else 0.0)
        if verdict == stop.GO:
            return
        reason = verdict.removeprefix("stop: ")
        if stop.is_hard(verdict):
            self.log.add("parked", reason=reason)
            raise Parked(reason)
        raise Stop(reason)

    # Steps.

    def write_tests(self, st_: history.Ticket):
        rejected = []
        while not st_.tests_done:
            answer = self.role("test_writer", {"ticket": self.ticket_text, "ticket_id":
                               self.ticket_id, "rejected": rejected})
            self.log.add("tests_written", cost_usd=answer.cost_usd,
                         tests=answer.data.get("tests"))
            review = self.role("reviewer", {"ticket": self.ticket_text,
                               "tests": answer.data.get("tests", [])}, lens="test_fit")
            missing = [i.id for i in self.ticket.items if i.must and not any(
                t.get("item") == i.id for t in answer.data.get("tests", []))]
            findings = review.data.get("findings", []) + [
                {"level": "blocking", "text": f"must-have item {m} has no test"} for m in missing]
            blocking = review.data.get("verdict") == "fail" or any(
                f.get("level") == "blocking" for f in findings)
            if not blocking:
                # The other checks, such as style, run on the new tests now. The builder
                # may not change a locked test, so a failure there must go back here.
                others = [n for n in self.settings["checks"] if n != "tests"]
                found = checks.run(self.settings, self.copy, others) if others else None
                failed = [c for c in (found.checks if found else []) if not c.passed]
                if failed:
                    findings = [{"level": "blocking", "text": f"check {c.name} fails on the "
                                 f"new tests:\n{c.output}"} for c in failed]
                else:
                    self.log.add("tests_reviewed", cost_usd=review.cost_usd)
                    st_.tests_done = True
                    break
            st_.rejections += 1
            self.log.add("tests_rejected", cost_usd=review.cost_usd, findings=findings)
            if st_.rejections > MAX_REJECTIONS:
                raise Stop(f"the tests were rejected {st_.rejections} times")
            rejected = findings

    def freeze(self, st_: history.Ticket):
        commit = self.commit(f"test({self.ticket_id}): the ticket and its locked tests")
        fetch_branch(self.project, self.copy, self.branch)
        try:
            self.store.freeze(self.ticket_id)
        except (StoreError, mf.FreezeError) as err:
            st_.rejections += 1
            st_.tests_done = False
            self.log.add("tests_rejected", findings=[{"level": "blocking", "text": str(err)}])
            if st_.rejections > MAX_REJECTIONS:
                raise Stop(f"the freeze refused the tests: {err}") from None
            return
        lock = self.lock() or {}
        self.log.add("frozen", commit=lock.get("commit", commit), number=lock.get("number"))
        st_.frozen = lock.get("commit", commit)
        st_.best_commit = st_.best_commit or st_.frozen

    def try_once(self, st_: history.Ticket):
        """One try, from the best try so far."""
        n = st_.attempts + 1
        git(self.copy, "reset", "-q", "--hard", st_.best_commit)
        git(self.copy, "clean", "-q", "-fd")
        last = [e for e in read(self.log_path) if e["event"] == "try_failed"]
        inputs = {"ticket": self.ticket_text, "attempt": n, "hint": st_.hint,
                  "findings": last[-1].get("findings", []) if last else [],
                  "failed": last[-1].get("failed", []) if last else [],
                  "check_output": last[-1].get("check_output", {}) if last else {}}
        self.log.add("try_started", attempt=n, start=st_.best_commit)
        stronger = self.settings["ai"]["stronger_builder"] if st_.stronger else ""
        if st_.stronger and not stronger:
            self.log.add("no_stronger_builder", attempt=n)
        try:
            answer = self.role("builder", inputs, command=stronger or None)
        except roles.RoleTimeout as err:
            self.log.add("try_failed", attempt=n, commit=st_.best_commit, score=-1,
                         timed_out=True, findings=[{"level": "blocking", "text": str(err)}])
            st_.attempts = n
            return
        cost = answer.cost_usd
        commit = self.commit(f"feat({self.ticket_id}): try {n}")
        results = self.checks()
        facts = self.gate.collect(self.project, self.copy, self.base, "HEAD", self.ticket_id,
                                  results)
        findings = self.gate.evaluate(facts)
        tier = self.gate.tier_of(facts)[0]
        lock = facts.lock or self.lock() or {"manifest": {"tests": []}}
        locked = {t: r["status"] for t, r in results.tests.items()
                  if t in lock["manifest"]["tests"]}
        failed_tests = sorted(t for t in lock["manifest"]["tests"] if locked.get(t) != "passed")
        key = [list(results.failed_checks()), failed_tests]
        fields = {"attempt": n, "commit": commit, "cost_usd": cost, "tier": tier,
                  "seconds": round(answer.seconds, 1),
                  "check_output": {c.name: c.output for c in results.checks if not c.passed},
                  "failed": [*key[0], *key[1]], "failed_key": key}
        st_.attempts = n
        cannot_fix = [f for f in findings if not f["fixable"] and f["check"] != "review"]
        if cannot_fix:
            self.log.add("try_failed", findings=findings, score=-1, **fields)
            raise Stop("the gate failed on a check the builder cannot fix: "
                       + "; ".join(f["message"] for f in cannot_fix))
        if any(f["fixable"] for f in findings):
            # The score with no review: a lower bound, so the best try can still move.
            value, passed = score(self.ticket, locked, [], self.copy)
            self.log.add("try_failed", findings=findings, score=value, items=passed, **fields)
            self._keep_if_best(st_, value, commit)
            return
        tested = sorted({item_of_test(t) for t in results.tests if item_of_test(t)})
        diff = self.review.diff(self.copy, st_.frozen, "HEAD")
        checked = self.role("reviewer", {"ticket": self.ticket_text, "tested": tested,
                                         "diff": diff}, lens="checklist")
        cost += checked.cost_usd
        value, passed = score(self.ticket, locked, checked.data.get("items", []), self.copy)
        blocking = [f for f in checked.data.get("findings", []) if f.get("level") == "blocking"]
        if tier >= 3:
            spent = []

            def run_role(lens, role_inputs):
                answer = self.role("reviewer", role_inputs, lens=lens)
                spent.append(answer.cost_usd)
                return answer.data
            facts.review_passed, found, _ = self.review.review(
                tier, self.ticket_text, self.review.diff(self.copy, self.base, "HEAD"), run_role)
            cost += sum(spent)
            blocking += [f for f in found if f.get("level") == "blocking"]
            findings = self.gate.evaluate(facts)
        fields.update(cost_usd=round(cost, 4), score=value, items=passed)
        must_failed = [i.id for i in self.ticket.items if i.must and not passed.get(i.id)]
        if findings or blocking or must_failed or value < self.settings["pass_score"]:
            why = blocking or [{"level": "major", "text": f["message"]} for f in findings] or [
                {"level": "major", "text": f"must-have items failed: {', '.join(must_failed)}"
                 if must_failed else f"score {value} is under {self.settings['pass_score']}"}]
            self.log.add("try_failed", findings=why, **fields)
            self._keep_if_best(st_, value, commit)
            if findings:
                raise Stop("the review of tier " + str(tier) + " failed: "
                           + "; ".join(f["message"] for f in findings))
            return
        try:
            record = self.gate.pass_record(facts, value)
        except self.gate.GateError as err:
            self.log.add("try_failed", findings=[{"level": "blocking", "text": str(err)}],
                         **fields)
            raise Stop(f"the gate refused a pass record: {err}") from None
        self.store.record_pass(facts.head_sha, record)
        self.log.add("try_passed", **fields)
        st_.passed_commit = commit
        self._keep_if_best(st_, value, commit)

    @staticmethod
    def _keep_if_best(st_: history.Ticket, value: int, commit: str):
        if history.better(value, st_.best_score):
            st_.best_score, st_.best_commit = value, commit

    def make_ready(self, st_: history.Ticket):
        git(self.copy, "reset", "-q", "--hard", st_.passed_commit)
        fetch_branch(self.project, self.copy, self.branch)
        self.store.ready(self.branch, self.ticket_id)
        st_.ready = st_.passed_commit
        self.log.add("ready", branch=self.branch, commit=st_.passed_commit)

    def finish(self, st_: history.Ticket) -> int:
        # A person merges tier 3 and 4, and any change whose tier the log does not show.
        tier = history.replay(read(self.log_path)).tier
        if not self.settings["auto_merge"] or tier is None or tier >= 3:
            self.log.add("waiting_for_merge", branch=self.branch, commit=st_.ready, tier=tier)
            return 0
        try:
            merge = self.store.merge(st_.ready)
        except StoreError as err:
            # The change stays ready; you merge it once the reason is gone.
            self.log.add("waiting_for_merge", branch=self.branch, commit=st_.ready, tier=tier,
                         reason=f"the store did not merge: {err}")
            return 0
        self.log.add("merged", commit=st_.ready, merge=merge)
        roles.remove_copy(self.project, self.ticket_id)
        return 0

    def ask_advisor(self, st_: history.Ticket, reason: str, person_only: bool = False) -> bool:
        """Return True to go on with one more try."""
        chain = ["person"] if person_only else self.settings["ai"]["advisor"]
        for entry in chain:
            if entry == "person":
                try:
                    found = advisor.ask_person(
                        self.store, self.log, self.log_path, f"ticket {self.ticket_id}", reason,
                        ["retry", "stronger", "split", "park"])
                except advisor.Waiting as waiting:
                    raise Parked(str(waiting)) from None
                return self._decided(st_, found["decision"], found["hint"], "a person")
            if st_.ai_decisions >= MAX_AI_DECISIONS:
                continue
            events = read(self.log_path)
            answer = self.role("advisor", {"ticket": self.ticket_text, "reason": reason,
                               "tries": [e for e in events
                                            if e["event"].startswith("try_")][-4:]},
                               command=entry)
            decision = answer.data.get("decision", "park")
            self.log.add("advisor_decided", by="ai", decision=decision, cost_usd=answer.cost_usd,
                         hint=answer.data.get("hint", ""), reason=answer.data.get("reason", ""))
            st_.ai_decisions += 1
            return self._decided(st_, decision, answer.data.get("hint", ""), "the advisor")
        self.log.add("parked", reason=reason)
        raise Parked(reason)

    def _decided(self, st_, decision: str, hint: str, who: str) -> bool:
        if decision in ("retry", "stronger") and st_.frozen:
            st_.hint = hint
            st_.stronger = st_.stronger or decision == "stronger"
            return True
        self.log.add("parked", reason=f"{who} chose {decision}")
        raise Parked(f"{who} chose {decision}")

    def run(self, until: str | None = None) -> int:
        """until="frozen" stops once the tests are frozen, for a roadmap's checklist."""
        self.until = until
        lock = run_lock(self.project, self.ticket_id)
        lock.acquire()
        try:
            st_ = history.replay(read(self.log_path))
            with Log(self.log_path, ticket=self.ticket_id, task=self.ticket.plan) as self.log:
                self.copy = roles.make_copy(self.project, self.ticket_id)
                if not st_.tests_done and not st_.frozen:
                    git(self.copy, "checkout", "-q", "-B", self.branch, self.base)
                    path = Path(self.copy, mf.ticket_path(self.ticket_id))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(self.ticket_text)
                self.settings = st.load_from_ref(self.copy, self.base)
                self.log.add("started", attempts_done=st_.attempts)
                question = advisor.pending(self.log_path)
                if question:
                    # Read the answer before doing anything else.
                    self.ask_advisor(st_, question["reason"], person_only=True)
                return self._loop(st_)
        except Parked:
            return 3
        finally:
            lock.release()

    def _loop(self, st_: history.Ticket) -> int:
        while True:
            try:
                while not st_.frozen:
                    self.write_tests(st_)
                    self.freeze(st_)
                if getattr(self, "until", None) == "frozen":
                    return 0
                while not st_.passed_commit:
                    self.stop_check()
                    self.try_once(st_)
                if not st_.ready:
                    self.make_ready(st_)
                return self.finish(st_)
            except Stop as stopped:
                self.log.add("stopped", reason=str(stopped))
                self.ask_advisor(st_, str(stopped))


def main(argv=None, store=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate driver", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--ticket", required=True)
    args = parser.parse_args(argv)
    try:
        return Driver(args.project, args.ticket, store).run()
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (roles.RoleError, tickets.TicketError, st.SettingsError, StoreError, OSError,
            subprocess.CalledProcessError) as err:
        print(f"driver: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
