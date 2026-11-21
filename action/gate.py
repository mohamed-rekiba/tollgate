"""The gate: six rules that decide whether a change may merge. It uses no AI.

`evaluate` checks facts and has no side effects. `collect` gathers the facts
from git and from the server. The command line joins the two.
"""

import argparse
import json
import sys
from dataclasses import dataclass, field

from action import manifest as mf
from action import settings as st
from action import tiers
from action.checks import Results
from action.gitio import GitError, changed_files, git
from action.paths import matches

FREEZE_WORKFLOW = ".github/workflows/tollgate-freeze.yml"
REVIEW_CHECK = "tollgate review"
GATE_CHECK = "tollgate gate"
BRANCH_PREFIX = "tg/"


@dataclass
class Freeze:
    number: int
    tag_commit: str
    manifest: dict
    run: dict | None = None  # path, head_branch, event, conclusion


@dataclass
class Facts:
    settings: dict
    branch: str
    head_sha: str
    changes: dict
    results: Results
    freeze: Freeze | None = None
    frozen_now_changed: list = field(default_factory=list)
    plan_required: bool = False
    plan_tickets: set | None = None
    pr_author: str = ""
    approvals: list = field(default_factory=list)
    review_passed: bool | None = None


def ticket_of(branch: str) -> str | None:
    if branch.startswith(BRANCH_PREFIX) and len(branch) > len(BRANCH_PREFIX):
        rest = branch[len(BRANCH_PREFIX):]
        if "/" not in rest:
            return rest
    return None


def approved(facts: Facts) -> bool:
    approvers = set(facts.settings["approvers"])
    for a in facts.approvals:
        if a["user_type"] != "User":
            continue
        if (a["kind"] == "review" and a["state"] == "APPROVED"
                and a["commit"] == facts.head_sha and a["user"] != facts.pr_author):
            return True
        if (a["kind"] == "comment" and a["user"] in approvers
                and a["body"] == f"tollgate approve {facts.head_sha}"):
            return True
    return False


def evaluate(facts: Facts) -> tuple:
    """Return (findings, tier). An empty list of findings means the change passes."""
    findings = []

    def fail(rule, message, file=""):
        findings.append({"rule": rule, "file": file, "message": message})

    ticket = ticket_of(facts.branch)
    freeze = facts.freeze
    frozen = set(freeze.manifest["files"]) if freeze else set()

    # Rule 1: ticket and freeze.
    if ticket is None:
        fail(1, f"the branch {facts.branch} is not named tg/<ticket id>")
    elif freeze is None:
        fail(1, f"no freeze exists for ticket {ticket}")
    else:
        m = freeze.manifest
        if m.get("ticket") != ticket:
            fail(1, f"the freeze is for ticket {m.get('ticket')}, not {ticket}")
        if m.get("commit") != freeze.tag_commit:
            fail(1, "the freeze tag does not point at the commit its manifest names")
        run = freeze.run
        if run is None:
            fail(1, "the run that created the freeze could not be checked")
        else:
            if run["path"] != FREEZE_WORKFLOW:
                fail(1, f"the freeze came from {run['path']}, not {FREEZE_WORKFLOW}")
            if run["head_branch"] != "main":
                fail(1, f"the freeze ran on {run['head_branch']}, not main")
            if run["event"] != "workflow_dispatch":
                fail(1, f"the freeze was started by {run['event']}, not by hand")
            if run["conclusion"] != "success":
                fail(1, "the freeze run did not succeed")

    # Rule 4 comes before rule 2, because rule 2 needs the tier.
    level, reason = tiers.tier(facts.settings, facts.changes, frozen)
    github = sorted(p for p in facts.changes if matches(p, [".github/**"]))
    for path in github:
        fail(4, "a change under .github/ is made outside Tollgate", path)
    needs_person = level == 4 or (freeze is not None and freeze.number > 1)
    if needs_person and not approved(facts):
        why = f"tier 4 ({reason})" if level == 4 else "a locked test was replaced"
        fail(4, f"{why}: needs an approval by a person on {facts.head_sha}")

    # Rule 2: plan.
    if facts.plan_required and level >= 2:
        if facts.plan_tickets is None:
            fail(2, "no approved plan exists for this ticket")
        elif ticket not in facts.plan_tickets:
            fail(2, f"the approved plan does not list ticket {ticket}")

    # Rule 3: locked files.
    for path in facts.frozen_now_changed:
        fail(3, "differs from the freeze", path)

    # Rule 5: checks and locked tests.
    for check in facts.results.checks:
        if not check.passed:
            fail(5, f"check {check.name} failed" + (" (time limit)" if check.timed_out else ""))
    if freeze:
        for test_id in freeze.manifest["tests"]:
            got = facts.results.tests.get(test_id)
            if got is None:
                fail(5, f"locked test did not run: {test_id}")
            elif got["status"] == "skipped":
                fail(5, f"locked test was skipped: {test_id}")
            elif got["status"] != "passed":
                fail(5, f"locked test failed: {test_id}")

    # Rule 6: review on the server.
    if level >= 3 and facts.review_passed is not True:
        state = "did not run" if facts.review_passed is None else "failed"
        fail(6, f"tier {level} needs the server review, which {state}")

    return findings, level


def _freeze(repo, ticket: str) -> Freeze | None:
    prefix = f"refs/tags/{BRANCH_PREFIX}freeze/{ticket}/"
    refs = git(repo, "for-each-ref", "--format=%(refname)", prefix).split()
    numbered = []
    for ref in refs:
        tail = ref[len(prefix):]
        if tail.isdigit():
            numbered.append((int(tail), ref))
    if not numbered:
        return None
    number, ref = max(numbered)
    message = git(repo, "for-each-ref", "--format=%(contents)", ref)
    commit = git(repo, "rev-parse", f"{ref}^{{commit}}").strip()
    return Freeze(number, commit, mf.loads(message))


def _plan_tickets(repo, plan: str) -> set | None:
    if not plan:
        return None
    prefix = f"refs/tags/{BRANCH_PREFIX}plan/{plan}/"
    refs = git(repo, "for-each-ref", "--format=%(refname)", prefix).split()
    numbered = [(int(r[len(prefix):]), r) for r in refs if r[len(prefix):].isdigit()]
    if not numbered:
        return None
    message = git(repo, "for-each-ref", "--format=%(contents)", max(numbered)[1])
    return set(mf.loads(message).get("tickets", []))


def collect(repo, base: str, head: str, branch: str, results: Results,
            server=None, pr: int | None = None) -> Facts:
    """Gather the facts. `base` names the main branch, for example origin/main."""
    settings = st.load_from_ref(repo, base)
    head_sha = git(repo, "rev-parse", head).strip()
    facts = Facts(settings, branch, head_sha, changed_files(repo, base, head), results)
    ticket = ticket_of(branch)
    if ticket:
        facts.freeze = _freeze(repo, ticket)
    if facts.freeze:
        facts.frozen_now_changed = mf.changed(facts.freeze.manifest, repo, head)
        run_id = facts.freeze.manifest.get("run_id")
        if server is not None and run_id:
            facts.freeze.run = server.run(run_id)
    facts.plan_required = bool(settings["require_plan"])
    if facts.plan_required and facts.freeze:
        from action.gitio import show_bytes
        from action.tickets import parse
        data = show_bytes(repo, facts.freeze.tag_commit, mf.ticket_path(ticket))
        plan = parse(data.decode()).plan if data else ""
        facts.plan_tickets = _plan_tickets(repo, plan)
    if server is not None and pr is not None:
        facts.pr_author = server.pull(pr)["author"]
        facts.approvals = server.approvals(pr)
        facts.review_passed = server.check_passed(head_sha, REVIEW_CHECK)
    return facts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate gate", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--branch", required=True)
    parser.add_argument("--results", required=True, help="results file from action.checks")
    parser.add_argument("--repository", help="owner/name, to ask the server")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--post", metavar="SHA",
                        help="post the result as the check 'tollgate gate' on this commit")
    args = parser.parse_args(argv)
    try:
        with open(args.results) as f:
            results = Results.from_json(f.read())
        server = None
        if args.repository:
            from action.server import Server
            server = Server(args.repository)
        facts = collect(args.repo, args.base, args.head, args.branch, results, server, args.pr)
        findings, level = evaluate(facts)
    except (GitError, st.SettingsError, mf.FreezeError, OSError, ValueError) as err:
        findings, level = [{"rule": 0, "file": "", "message": f"the gate could not run: {err}"}], 0
        _report(args, findings, level)
        return 2
    _report(args, findings, level)
    return 1 if findings else 0


def summary(findings: list, level: int) -> tuple:
    """Return (title, text) for a person to read."""
    if not findings:
        return f"Passed. Tier {level}.", f"Every gate rule passed. Tier {level}."
    title = f"Failed: {len(findings)} finding(s). Tier {level}."
    lines = [f"- Rule {f['rule']}: {f['message']}" + (f" (`{f['file']}`)" if f["file"] else "")
             for f in findings]
    return title, "\n".join(lines)


def _report(args, findings: list, level: int) -> None:
    for finding in findings:
        print(json.dumps(finding))
    print(json.dumps({"tier": level, "passed": not findings}))
    if args.post and args.repository:
        from action.server import Server
        title, text = summary(findings, level)
        Server(args.repository).post_check(args.post, GATE_CHECK, not findings, title, text)


if __name__ == "__main__":
    sys.exit(main())
