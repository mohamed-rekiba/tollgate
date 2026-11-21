"""The driver: build one ticket, steps 1 to 9, and stop when a stop rule says so.


Run state lives only in the log, .tollgate/logs/<ticket>.jsonl. A driver that
starts again reads the log and repeats no finished step.

Exit codes: 0 the pull request is open or merged, 3 the ticket waits for the
advisor or is parked, 4 another driver holds the ticket, 1 an error.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from action import checks, gate, prepare, tickets
from action import manifest as mf
from action import settings as st
from action.gitio import changed_files
from action.tickets import item_of_test
from driver import advisor, roles
from driver.log import Log, read

BUILDER_RULES = {3, 5}     # the builder can fix these
SERVER_RULES = {4, 6}      # met on the server, after the pull request opens
MAX_REJECTIONS = 2
MAX_AI_DECISIONS = 2
LENS_TIERS = ((2, "change"), (3, "security"))  # step 7: lens and the lowest tier it runs for


class Busy(RuntimeError):
    pass


class Stop(Exception):
    """A stop rule fired. The reason goes to the advisor."""


class Parked(Exception):
    pass


# The lock for each ticket.

class TicketLock:
    def __init__(self, path: str):
        self.path = path

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


# The driver.

@dataclass
class State:
    tests_done: bool = False
    frozen: str = ""
    rejections: int = 0
    attempts: int = 0
    best_commit: str = ""
    best_score: int = -1
    last_failed: tuple = ()
    passed_commit: str = ""
    pr: int = 0
    extra_attempts: int = 0
    ai_decisions: int = 0
    hint: str = ""
    stronger: bool = False

    @classmethod
    def from_events(cls, events: list) -> "State":
        s = cls()
        for e in events:
            kind = e["event"]
            if kind == "tests_reviewed":
                s.tests_done = True
            elif kind == "tests_rejected":
                s.rejections += 1
            elif kind == "frozen":
                s.frozen = e["tag"]
                s.best_commit = s.best_commit or e["commit"]
            elif kind in ("attempt_failed", "attempt_passed"):
                s.attempts = e["attempt"]
                s.last_failed = tuple(map(tuple, e.get("failed_key", [[], []])))
                if e.get("score", -1) > s.best_score:
                    s.best_score, s.best_commit = e["score"], e["commit"]
                if kind == "attempt_passed":
                    s.passed_commit = e["commit"]
            elif kind == "pr_opened":
                s.pr = e["pr"]
            elif kind == "advisor_decided":
                s.ai_decisions += 1 if e.get("by") == "ai" else 0
                if e["decision"] in ("retry", "stronger"):
                    s.extra_attempts += 1
                    s.hint = e.get("hint", "")
                    s.stronger = s.stronger or e["decision"] == "stronger"
        return s


NETWORK = {"fetch", "push", "pull", "clone", "ls-remote"}


def _auth() -> list:
    """On GitHub Actions, the token from the environment, for one network command. It
    never goes into a saved config that the project's checks could read."""
    token = os.environ.get("GH_TOKEN") if os.environ.get("GITHUB_ACTIONS") == "true" else ""
    if not token:
        return []
    import base64
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {basic}"]


def git(cwd, *args) -> str:
    auth = _auth() if args and args[0] in NETWORK else []
    return subprocess.run(["git", *auth, *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def push(cwd, *args) -> str:
    return git(cwd, "push", *args)


def cost_of(events: list) -> float:
    return round(sum(float(e.get("cost_usd") or 0) for e in events), 4)


def task_cost(logs_dir: str, task: str) -> float:
    total = 0.0
    for path in Path(logs_dir).glob("*.jsonl"):
        total += cost_of([e for e in read(str(path)) if e.get("task") == task])
    return round(total, 4)


class Driver:
    def __init__(self, project: str, ticket_id: str, server, base: str = "origin/main"):
        self.project = os.path.abspath(project)
        self.ticket_id = ticket_id
        self.server = server
        self.base = base
        self.branch = f"tg/{ticket_id}"
        self.logs = os.path.join(self.project, ".tollgate", "logs")
        self.log_path = os.path.join(self.logs, f"{ticket_id}.jsonl")
        self.ticket_text = Path(self.project, mf.ticket_path(ticket_id)).read_text()
        self.ticket = tickets.parse(self.ticket_text)

    # Helpers.

    def role(self, name, inputs, minutes, lens=None, command=None):
        s = self.settings
        command = command or (s["ai"]["reviewer"] if name == "reviewer" else s["ai"]["builder"])
        answer = roles.run(command, name, inputs, self.copy, minutes, lens,
                           s["sandbox"], s["container_image"])
        return answer

    def spend(self, answer) -> float:
        return round(answer.cost_usd, 4)

    def checks(self, only=None):
        manifest = None
        freeze = gate._freeze(self.copy, self.ticket_id)
        if freeze:
            manifest = freeze.manifest
        prepare.restore(self.copy, self.base, freeze.tag_commit if freeze else None, manifest)
        try:
            for command in self.settings["setup"]:
                subprocess.run(command, shell=True, cwd=self.copy, check=False,
                               capture_output=True)
            return checks.run(self.settings, self.copy, only)
        finally:
            git(self.copy, "reset", "-q", "--hard", "HEAD")
            git(self.copy, "clean", "-q", "-fd")

    def changed_github(self) -> list:
        out = git(self.copy, "status", "--porcelain", "-z", "--untracked-files=all")
        paths = [entry[3:] for entry in out.split("\0") if len(entry) > 3]
        committed = changed_files(self.copy, self.base, "HEAD")
        return sorted(p for p in {*paths, *committed} if p.startswith(".github/"))

    def commit(self, message) -> str:
        bad = self.changed_github()
        for path in bad:
            # Put back the main branch's copy, or remove the file if main has none.
            git(self.copy, "rm", "-q", "-f", "--ignore-unmatch", "--", path)
            if git(self.copy, "ls-tree", self.base, "--", path):
                git(self.copy, "checkout", "-q", self.base, "--", path)
        git(self.copy, "add", "-A")
        git(self.copy, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.copy, "rev-parse", "HEAD"), bad

    # Steps.

    def write_tests(self, st_: State):
        rejected = []
        while not st_.tests_done:
            answer = self.role("test_writer", {"ticket": self.ticket_text, "ticket_id":
                               self.ticket_id, "rejected": rejected},
                               self.settings["stop"]["attempt_minutes"])
            self.log.add("tests_written", cost_usd=self.spend(answer), tests=answer.data.get("tests"))
            review = self.role("reviewer", {"ticket": self.ticket_text,
                               "tests": answer.data.get("tests", [])},
                               self.settings["stop"]["attempt_minutes"], lens="test_fit")
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
                    self.log.add("tests_reviewed", cost_usd=self.spend(review))
                    st_.tests_done = True
                    break
            st_.rejections += 1
            self.log.add("tests_rejected", cost_usd=self.spend(review), findings=findings)
            if st_.rejections > MAX_REJECTIONS:
                raise Stop(f"the tests were rejected {st_.rejections} times")
            rejected = findings

    def freeze(self, st_: State):
        commit, bad = self.commit(f"{self.ticket_id}: ticket and locked tests")
        bad = bad or self.changed_github()
        if bad:
            raise Stop(f"the test writer changed files under .github: {bad}")
        push(self.copy, "-q", "-f", "origin", f"HEAD:refs/heads/{self.branch}")
        try:
            tag = self.server.freeze(self.ticket_id)
        except mf.FreezeError as err:
            st_.rejections += 1
            st_.tests_done = False
            self.log.add("tests_rejected", findings=[{"level": "blocking", "text": str(err)}])
            if st_.rejections > MAX_REJECTIONS:
                raise Stop(f"the freeze refused the tests: {err}") from None
            return
        git(self.copy, "fetch", "-q", "origin", "--tags", "--force")
        self.log.add("frozen", tag=tag, commit=commit)
        st_.frozen = tag
        st_.best_commit = st_.best_commit or commit

    def stop_rules(self, st_: State, events: list):
        s = self.settings["stop"]
        if st_.attempts >= s["attempts"] + st_.extra_attempts:
            raise Stop(f"the ticket used {st_.attempts} attempts")
        if cost_of(events) >= s["ticket_usd"]:
            raise Stop(f"the ticket cost {cost_of(events)} USD")
        if task_cost(self.logs, self.ticket.plan) >= s["task_usd"]:
            raise Stop(f"the task reached {s['task_usd']} USD")

    def attempt(self, st_: State):
        n = st_.attempts + 1
        git(self.copy, "reset", "-q", "--hard", st_.best_commit)
        git(self.copy, "clean", "-q", "-fd")
        last = [e for e in read(self.log_path) if e["event"] == "attempt_failed"]
        inputs = {"ticket": self.ticket_text, "attempt": n, "hint": st_.hint,
                  "findings": last[-1].get("findings", []) if last else [],
                  "failed": last[-1].get("failed", []) if last else [],
                  "check_output": last[-1].get("check_output", {}) if last else {}}
        self.log.add("attempt_started", attempt=n)
        try:
            stronger = self.settings["ai"]["stronger_builder"] if st_.stronger else ""
            answer = self.role("builder", inputs, self.settings["stop"]["attempt_minutes"],
                               command=stronger or None)
            if st_.stronger and not stronger:
                self.log.add("no_stronger_builder", attempt=n)
        except roles.RoleError as err:
            if "ran past" in str(err):
                raise Stop(f"attempt {n} ran for {self.settings['stop']['attempt_minutes']} "
                           "minutes") from None
            raise
        cost = self.spend(answer)
        commit, bad = self.commit(f"{self.ticket_id}: attempt {n}")
        results = self.checks()
        facts = gate.collect(self.copy, self.base, "HEAD", self.branch, results, self.server)
        findings, tier = gate.evaluate(facts)
        findings = [f for f in findings if f["rule"] not in SERVER_RULES or
                    f["file"].startswith(".github/")]
        findings += [{"rule": 4, "file": p, "message": "the driver refused a change under .github"}
                     for p in bad]
        failed_tests = sorted(t for t, r in results.tests.items() if r["status"] != "passed"
                              and t in (facts.freeze.manifest["tests"] if facts.freeze else []))
        key = (tuple(results.failed_checks()), tuple(failed_tests))
        fields = {"attempt": n, "commit": commit, "cost_usd": cost, "tier": tier,
                  "check_output": {c.name: c.output for c in results.checks if not c.passed},
                  "failed": [*results.failed_checks(), *failed_tests],
                  "failed_key": [list(key[0]), list(key[1])]}
        other = [f for f in findings if f["rule"] not in BUILDER_RULES]
        if other:
            self.log.add("attempt_failed", findings=findings, score=-1, **fields)
            st_.attempts = n
            raise Stop("the gate failed on a rule the builder cannot fix: "
                       + "; ".join(f["message"] for f in other))
        if findings:
            self.log.add("attempt_failed", findings=findings, score=-1, **fields)
            same = key == st_.last_failed and any(key)
            st_.attempts, st_.last_failed = n, key
            if same:
                raise Stop("the same checks failed as in the attempt before")
            return
        tested = sorted({item_of_test(t) for t in results.tests if item_of_test(t)})
        review = self.role("reviewer", {
            "ticket": self.ticket_text, "tested": tested,
            "diff": git(self.copy, "diff", f"{st_.frozen}...HEAD")[:60000]},
            self.settings["stop"]["attempt_minutes"], lens="checklist")
        cost += self.spend(review)
        locked = {t: r["status"] for t, r in results.tests.items()
                  if facts.freeze and t in facts.freeze.manifest["tests"]}
        value, passed = score(self.ticket, locked, review.data.get("items", []), self.copy)
        blocking = [f for f in review.data.get("findings", []) if f.get("level") == "blocking"]
        for lens in [name for level, name in LENS_TIERS if tier >= level]:
            more = self.role("reviewer", {"ticket": self.ticket_text, "tier": tier,
                             "diff": git(self.copy, "diff", f"{st_.frozen}...HEAD")[:60000]},
                             self.settings["stop"]["attempt_minutes"], lens=lens)
            cost += self.spend(more)
            blocking += [dict(f, lens=lens) for f in more.data.get("findings", [])
                         if f.get("level") == "blocking"]
        fields.update(cost_usd=cost, score=value, items=passed)
        if blocking or value < self.settings["pass_score"]:
            self.log.add("attempt_failed", findings=blocking or [
                {"level": "major", "text": f"score {value} is under {self.settings['pass_score']}"}],
                **fields)
            st_.attempts, st_.last_failed = n, key
            if value > st_.best_score:
                st_.best_score, st_.best_commit = value, commit
            return
        self.log.add("attempt_passed", **fields)
        st_.attempts, st_.passed_commit = n, commit

    def open_pr(self, st_: State):
        git(self.copy, "reset", "-q", "--hard", st_.passed_commit)
        if self.changed_github() or any(p.startswith(".github/") for p in changed_files(
                self.copy, self.base, "HEAD")):
            raise Stop("the change touches .github; the driver does not push it")
        push(self.copy, "-q", "-f", "origin", f"HEAD:refs/heads/{self.branch}")
        events = read(self.log_path)
        passed = [e for e in events if e["event"] == "attempt_passed"][-1]
        notes = []
        if self.settings["sandbox"] == "none":
            notes.append("The builder ran with no sandbox.")
        if not self.settings["auto_merge"]:
            notes.append("auto_merge is off: a person merges this.")
        body = (f"Ticket {self.ticket_id}. Tier {passed['tier']}. Score {passed['score']}. "
                f"Attempts {passed['attempt']}. Cost {cost_of(events)} USD.\n\n"
                + "\n".join(notes))
        st_.pr = self.server.open_pr(self.branch, f"{self.ticket_id}: {self.ticket.id}", body)
        self.log.add("pr_opened", pr=st_.pr, commit=st_.passed_commit)

    def finish(self, st_: State) -> int:
        if not self.settings["auto_merge"]:
            self.log.add("waiting_for_merge", pr=st_.pr)
            return 0
        result = self.server.wait_gate(st_.passed_commit)
        if result != "success":
            raise Stop(f"the gate on the server says {result}")
        self.server.merge(st_.pr)
        self.log.add("merged", pr=st_.pr)
        roles.remove_copy(self.project, self.ticket_id)
        return 0

    def ask_advisor(self, st_: State, reason: str, person_only: bool = False) -> bool:
        """Return True to go on with one more attempt."""
        chain = ["person"] if person_only else self.settings["ai"]["advisor"]
        for entry in chain:
            if entry == "person":
                try:
                    found = advisor.ask_person(
                        self.server, self.log, self.log_path, f"ticket {self.ticket_id}", reason,
                        ["retry", "stronger", "split", "park"], self.settings["approvers"])
                except advisor.Waiting as waiting:
                    raise Parked(str(waiting)) from None
                if found["decision"] in ("retry", "stronger") and st_.frozen:
                    st_.extra_attempts += 1
                    st_.hint = found["hint"]
                    st_.stronger = st_.stronger or found["decision"] == "stronger"
                    return True
                self.log.add("parked", reason=f"a person chose {found['decision']}")
                raise Parked(f"a person chose {found['decision']}")
            if st_.ai_decisions >= MAX_AI_DECISIONS:
                continue
            events = read(self.log_path)
            answer = self.role("advisor", {"ticket": self.ticket_text, "reason": reason,
                               "attempts": [e for e in events if e["event"].startswith("attempt_")][-4:]},
                               self.settings["stop"]["attempt_minutes"], command=entry)
            decision = answer.data.get("decision", "park")
            self.log.add("advisor_decided", by="ai", decision=decision, cost_usd=self.spend(answer),
                         hint=answer.data.get("hint", ""), reason=answer.data.get("reason", ""))
            st_.ai_decisions += 1
            if decision in ("retry", "stronger") and st_.frozen:
                st_.extra_attempts += 1
                st_.hint = answer.data.get("hint", "")
                st_.stronger = st_.stronger or decision == "stronger"
                return True
            self.log.add("parked", reason=f"advisor chose {decision}")
            raise Parked(f"advisor chose {decision}")
        self.log.add("parked", reason=reason)
        raise Parked(reason)

    def run(self, until: str | None = None) -> int:
        """until="frozen" stops once the tests are frozen, for a roadmap's checklist."""
        self.until = until
        lock = TicketLock(os.path.join(self.project, ".tollgate", "run", f"{self.ticket_id}.lock"))
        lock.acquire()
        try:
            st_ = State.from_events(read(self.log_path))
            with Log(self.log_path, ticket=self.ticket_id, task=self.ticket.plan) as self.log:
                self.copy = roles.make_copy(self.project, self.ticket_id)
                git(self.copy, "fetch", "-q", "origin", "--tags", "--force")
                if not st_.tests_done and not st_.frozen:
                    git(self.copy, "checkout", "-q", "-B", self.branch, self.base)
                    Path(self.copy, mf.ticket_path(self.ticket_id)).parent.mkdir(
                        parents=True, exist_ok=True)
                    Path(self.copy, mf.ticket_path(self.ticket_id)).write_text(self.ticket_text)
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

    def _loop(self, st_: State) -> int:
        while True:
            try:
                while not st_.frozen:
                    self.write_tests(st_)
                    self.freeze(st_)
                if getattr(self, "until", None) == "frozen":
                    return 0
                while not st_.passed_commit:
                    self.stop_rules(st_, read(self.log_path))
                    self.attempt(st_)
                if not st_.pr:
                    self.open_pr(st_)
                return self.finish(st_)
            except Stop as stop:
                self.log.add("stopped", reason=str(stop))
                self.ask_advisor(st_, str(stop))


def main(argv=None, server=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate driver", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--repository", help="owner/name; read from origin when left out")
    args = parser.parse_args(argv)
    if server is None:
        from driver.server import GitHub
        server = GitHub.for_project(args.project, args.repository)
    try:
        return Driver(args.project, args.ticket, server).run()
    except Busy as err:
        print(err, file=sys.stderr)
        return 4
    except (roles.RoleError, tickets.TicketError, st.SettingsError, OSError,
            subprocess.CalledProcessError) as err:
        print(f"driver: {err}", file=sys.stderr)
        return 1

