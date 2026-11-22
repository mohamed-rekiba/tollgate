"""The gate: six checks that decide whether a try passes. It uses no AI.

The driver runs it on your machine after each try. `collect` gathers the facts
from git and the state folder. `evaluate` checks them and has no side effects.
`pass_record` builds the record the store signs when a try passes.

The six checks:

    lock          the ticket's lock verifies, matches its commit, and adds only tests and the ticket
    plan          a verified plan lock lists the ticket (tier 1 needs none)
    locked_files  every locked file has its fingerprint at the try
    tier          the tier, from the files the try changes
    tests         every check passes and every locked test ran and passed
    review        tier 2 and up need a passed review

Approvals are not checked here: the store checks them at merge.
"""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field

from gate import settings as st
from gate import sign, state, tiers
from gate.checks import Results
from gate.gitio import GitError, changed_files, fingerprint, git, show_bytes
from gate.manifest import ticket_path

BRANCH_PREFIX = "tg/"
CHECKS = ("lock", "plan", "locked_files", "tier", "tests", "review")
# Findings of these checks are the builder's to fix in a next try.
FIXABLE = {"locked_files", "tests"}
# Today's rule numbers, for people who read a finding.
RULES = {"lock": 1, "plan": 2, "locked_files": 3, "tier": 4, "tests": 5, "review": 6}


class GateError(ValueError):
    """The gate refuses a step. The message says why."""


@dataclass
class Facts:
    settings: dict             # from main, never from the try
    ticket: str
    head_sha: str
    changes: dict              # path -> lines changed, from main to the try
    results: Results
    lock: dict | None = None   # the verified lock record
    lock_error: str = ""       # why there is no verified lock
    lock_sha256: str = ""      # of the lock record's exact bytes
    lock_files_differ: list = field(default_factory=list)  # locked files that differ at the lock commit
    lock_commit_files: list = field(default_factory=list)  # files the lock commit changed
    lock_in_history: bool = True   # the lock commit is an ancestor of the try
    locked_now_changed: list = field(default_factory=list)  # locked files that differ at the try
    plan_task: str = ""
    plan: dict | None = None   # the verified plan lock
    plan_error: str = ""
    review_passed: bool | None = None  # the review verdict the driver hands in


def ticket_of(branch: str) -> str | None:
    if branch.startswith(BRANCH_PREFIX) and len(branch) > len(BRANCH_PREFIX):
        rest = branch[len(BRANCH_PREFIX):]
        if "/" not in rest:
            return rest
    return None


def locked_files(facts: Facts) -> set:
    return set(facts.lock["manifest"]["files"]) if facts.lock else set()


def tier_of(facts: Facts) -> tuple:
    """Return (tier, reason)."""
    return tiers.tier(facts.settings, facts.changes, locked_files(facts))


def evaluate(facts: Facts) -> list:
    """Return the findings. An empty list means the try passes.

    Each finding is {check, rule, file, message, fixable}. fixable is true when
    the builder can fix it in a next try.
    """
    findings = []

    def fail(check, message, file=""):
        findings.append({"check": check, "rule": RULES[check], "file": file,
                         "message": message, "fixable": check in FIXABLE})

    ticket = facts.ticket
    lock = facts.lock

    # Lock.
    if lock is None:
        fail("lock", facts.lock_error or f"ticket {ticket} has no lock")
    else:
        if facts.lock_error:
            fail("lock", facts.lock_error)
        if lock.get("ticket") != ticket:
            fail("lock", f"the lock is for ticket {lock.get('ticket')}, not {ticket}")
        if not facts.lock_in_history:
            fail("lock", f"the try is not built on the lock commit {lock.get('commit')}")
        for path in facts.lock_files_differ:
            fail("lock", "differs from the lock at the lock commit", path)
        allowed = set(lock["manifest"]["files"])
        if ticket_path(ticket) not in allowed:
            fail("lock", "the lock does not hold the ticket file", ticket_path(ticket))
        for path in facts.lock_commit_files:
            if path not in allowed:
                fail("lock", "the lock commit changed a file that is not a test or the ticket",
                     path)

    level, reason = tier_of(facts)

    # Plan.
    if facts.settings["require_plan"] and level >= 2:
        plan = facts.plan
        if plan is None:
            fail("plan", facts.plan_error or f"no approved plan lists ticket {ticket}")
        elif plan.get("task") != facts.plan_task:
            fail("plan", f"the plan lock is for {plan.get('task')}, not {facts.plan_task}")
        elif ticket_path(ticket) not in plan.get("files", {}):
            fail("plan", f"the approved plan does not list ticket {ticket}")
        elif lock and plan["files"][ticket_path(ticket)] != \
                lock["manifest"]["files"].get(ticket_path(ticket)):
            fail("plan", "the ticket differs from the one in the approved plan",
                 ticket_path(ticket))

    # Locked files.
    for path in facts.locked_now_changed:
        fail("locked_files", "differs from the lock", path)

    # Tier: it only sets the tier, which the review check and the store use.

    # Tests and checks.
    for check in facts.results.checks:
        if not check.passed:
            fail("tests", f"check {check.name} failed" + (" (time limit)" if check.timed_out else ""))
    if lock:
        for test_id in lock["manifest"]["tests"]:
            got = facts.results.tests.get(test_id)
            if got is None:
                fail("tests", f"locked test did not run: {test_id}")
            elif got["status"] == "skipped":
                fail("tests", f"locked test was skipped: {test_id}")
            elif got["status"] != "passed":
                fail("tests", f"locked test failed: {test_id}")

    # Review.
    if level >= 2 and facts.review_passed is not True:
        state_ = "did not run" if facts.review_passed is None else "failed"
        fail("review", f"tier {level} ({reason}) needs a passed review; the review {state_}")

    return findings


def checks_of(findings: list) -> dict:
    """{check: passed} for each of the six checks."""
    failed = {f["check"] for f in findings}
    return {name: name not in failed for name in CHECKS}


def pass_record(facts: Facts, score: int, at: str | None = None) -> dict:
    """Build the pass record of a try. The store signs and writes it.

    Refuse a try with any finding or a score below pass_score: a failed try
    never gets a pass record.
    """
    findings = evaluate(facts)
    if findings:
        raise GateError(f"the try has {len(findings)} finding(s): {findings[0]['message']}")
    if score < facts.settings["pass_score"]:
        raise GateError(f"score {score} is below {facts.settings['pass_score']}")
    return {
        "commit": facts.head_sha,
        "ticket": facts.ticket,
        "tier": tier_of(facts)[0],
        "lock_sha256": facts.lock_sha256,
        "checks": checks_of(findings),
        "score": score,
        "at": at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _read(project: str, kind: str, name: str, namespace: str, signers: list) -> tuple:
    """Return (record, sha256 of its bytes, error)."""
    path = state.path(project, kind, f"{name}.json")
    try:
        record = sign.read(path, namespace, signers)
    except (sign.SignError, ValueError) as err:
        return None, "", str(err)
    return record, hashlib.sha256(path.read_bytes()).hexdigest(), ""


def _differ(repo, ref: str, files: dict) -> list:
    out = []
    for path, print_ in sorted(files.items()):
        data = show_bytes(repo, ref, path)
        if data is None or fingerprint(data) != print_:
            out.append(path)
    return out


def _is_ancestor(repo, commit: str, head: str) -> bool:
    try:
        git(repo, "merge-base", "--is-ancestor", commit, head)
    except GitError:
        return False
    return True


def _chain_changed(project: str, repo, base: str, head_sha: str, ticket: str,
                   signers: list) -> list:
    """The locked files of the other tickets this try builds on, and that are not on main
    yet, which differ at the try. In a task each ticket starts from the ready change
    before it, so its try holds the earlier tickets' locked tests too."""
    out = []
    folder = state.state_dir(project) / "locks"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        if path.stem == ticket:
            continue
        try:
            commit = json.loads(path.read_text()).get("commit") or ""
        except (OSError, ValueError, AttributeError):
            continue
        if not commit or not _is_ancestor(repo, commit, head_sha) or _is_ancestor(repo, commit,
                                                                                    base):
            continue
        other, _, _ = _read(project, "locks", path.stem, "tollgate-lock", signers)
        if other:
            out += _differ(repo, head_sha, other["manifest"]["files"])
    return out


def collect(project: str, repo, base: str, head: str, ticket: str, results: Results,
            review_passed: bool | None = None, start: str | None = None) -> Facts:
    """Gather the facts.

    project names the state folder. repo is the copy that holds the try.
    base names the main branch: the settings, and so the signers, come from there.
    start is the commit the ticket started from, when not base: the tier counts only
    the files changed since then. It must be the base the store recorded in the lock.
    """
    settings = st.load_from_ref(repo, base)
    signers = settings["signers"]
    head_sha = git(repo, "rev-parse", head).strip()
    facts = Facts(settings, ticket, head_sha, changed_files(repo, start or base, head), results,
                  review_passed=review_passed)
    lock, digest, error = _read(project, "locks", ticket, "tollgate-lock", signers)
    if lock is None:
        facts.lock_error = f"the lock of ticket {ticket} does not verify: {error}"
        return facts
    facts.lock, facts.lock_sha256 = lock, digest
    if start and git(repo, "rev-parse", start).strip() != lock.get("base_commit"):
        # The store checked the start of the lock; any other start is not trusted.
        facts.lock_error = f"the ticket's start {start[:12]} is not the base of its lock"
    files = lock["manifest"]["files"]
    commit = lock["commit"]
    try:
        git(repo, "merge-base", "--is-ancestor", commit, head_sha)
    except GitError:
        facts.lock_in_history = False
    facts.lock_files_differ = _differ(repo, commit, files)
    try:
        facts.lock_commit_files = sorted(changed_files(repo, lock["base_commit"], commit))
    except GitError as err:
        facts.lock_error = f"the lock commit cannot be compared to its base: {err}"
    facts.locked_now_changed = _differ(repo, head_sha, files)
    facts.locked_now_changed += [p for p in _chain_changed(project, repo, base, head_sha, ticket,
                                                           signers)
                                 if p not in facts.locked_now_changed]

    data = show_bytes(repo, commit, ticket_path(ticket))
    if data is not None:
        from gate.tickets import parse
        try:
            facts.plan_task = parse(data.decode()).plan
        except ValueError as err:
            facts.plan_error = f"the ticket cannot be read: {err}"
    if facts.plan_task:
        plan, _, error = _read(project, "plans", facts.plan_task, "tollgate-plan", signers)
        facts.plan = plan
        if plan is None:
            facts.plan_error = f"the plan lock of {facts.plan_task} does not verify: {error}"
    elif not facts.plan_error:
        facts.plan_error = "the ticket names no plan"
    return facts


def summary(findings: list, level: int) -> tuple:
    """Return (title, text) for a person to read."""
    if not findings:
        return f"Passed. Tier {level}.", f"Every gate check passed. Tier {level}."
    title = f"Failed: {len(findings)} finding(s). Tier {level}."
    lines = [f"- Rule {f['rule']}: {f['message']}" + (f" (`{f['file']}`)" if f["file"] else "")
             for f in findings]
    return title, "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate gate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".", help="the project, which names the state folder")
    parser.add_argument("--repo", default=".", help="the copy that holds the try")
    parser.add_argument("--base", default="main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--results", required=True, help="results file from gate.checks")
    parser.add_argument("--review", choices=("passed", "failed"),
                        help="the review verdict, for tier 2 and up")
    args = parser.parse_args(argv)
    review = {"passed": True, "failed": False}.get(args.review)
    try:
        with open(args.results) as f:
            results = Results.from_json(f.read())
        facts = collect(args.project, args.repo, args.base, args.head, args.ticket, results,
                        review)
        findings, level = evaluate(facts), tier_of(facts)[0]
    except Exception as err:  # noqa: BLE001 - any failure must fail the try
        print(json.dumps({"check": "", "rule": 0, "file": "", "fixable": False,
                          "message": f"the gate could not run: {err}"}))
        return 2
    for finding in findings:
        print(json.dumps(finding))
    print(json.dumps({"tier": level, "passed": not findings}))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
