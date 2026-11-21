"""Tests for the gate: each rule has a case that passes and a case that fails."""

import unittest

from action import gate, settings
from action import manifest as mf
from action.checks import CheckResult, Results
from tests.helpers import TICKET, Repo, settings_text

HEAD = "a" * 40
TESTS = ["tests.test_t1::test_c1_retries", "tests.test_t1::test_c2_sent_once"]
GOOD_RUN = {"path": gate.FREEZE_WORKFLOW, "head_branch": "main",
            "event": "workflow_dispatch", "conclusion": "success"}


def passing_results():
    return Results([CheckResult("tests", True)], {t: {"status": "passed", "file": ""} for t in TESTS})


def facts(**over):
    s = settings.parse('{"approvers": ["owner"]}')
    m = {"ticket": "T-1", "commit": "c" * 40, "files": {"tests/test_t1.py": "x"}, "tests": TESTS,
         "number": 1}
    run = dict(GOOD_RUN, title="tollgate freeze T-1", manifest=m)
    f = gate.Freeze(1, "c" * 40, m, run)
    f = gate.Facts(
        settings=s, branch="tg/T-1", head_sha=HEAD, changes={"src/retry.py": 20},
        results=passing_results(), freeze=f,
        pr_author="owner",
    )
    for k, v in over.items():
        setattr(f, k, v)
    return f


def rules(f):
    return sorted({x["rule"] for x in gate.evaluate(f)[0]})


class GateRulesTest(unittest.TestCase):
    def test_a_clean_change_passes(self):
        findings, level = gate.evaluate(facts())
        self.assertEqual(findings, [])
        self.assertEqual(level, 1)

    def test_rule1_branch_must_name_a_ticket(self):
        self.assertEqual(rules(facts(branch="feature/x")), [1])

    def test_rule1_needs_a_freeze(self):
        self.assertIn(1, rules(facts(freeze=None)))

    def test_rule1_freeze_from_another_workflow_fails(self):
        f = facts()
        f.freeze.run["path"] = ".github/workflows/fake.yml"
        self.assertEqual(rules(f), [1])

    def test_rule1_freeze_run_on_a_branch_fails(self):
        f = facts()
        f.freeze.run["head_branch"] = "tg/T-1"
        self.assertEqual(rules(f), [1])

    def test_rule1_moved_tag_fails(self):
        f = facts()
        f.freeze.tag_commit = "d" * 40
        self.assertEqual(rules(f), [1])

    def test_rule1_unchecked_run_fails(self):
        f = facts()
        f.freeze.run = None
        self.assertEqual(rules(f), [1])

    def test_rule2_plan_required(self):
        self.assertEqual(rules(facts(plan_required=True, changes={"src/a.py": 80})), [2])
        ok = facts(plan_required=True, plan_tickets={"T-1"}, changes={"src/a.py": 80})
        self.assertEqual(rules(ok), [])

    def test_rule2_not_needed_for_tier_1(self):
        self.assertEqual(rules(facts(plan_required=True)), [])

    def test_rule3_changed_frozen_file(self):
        self.assertEqual(rules(facts(frozen_now_changed=["tests/test_t1.py"])), [3])

    def test_rule4_tier_4_needs_approval(self):
        f = facts(changes={"pyproject.toml": 2}, review_passed=True)
        self.assertEqual(rules(f), [4])
        f.approvals = [{"kind": "comment", "user": "owner", "user_type": "User",
                        "body": f"tollgate approve {HEAD}", "state": "", "commit": ""}]
        self.assertEqual(rules(f), [])

    def test_rule4_approval_must_name_the_latest_commit_and_come_from_an_approver(self):
        stale = {"kind": "comment", "user": "owner", "user_type": "User",
                 "body": "tollgate approve " + "b" * 40, "state": "", "commit": ""}
        stranger = {"kind": "comment", "user": "someone", "user_type": "User",
                    "body": f"tollgate approve {HEAD}", "state": "", "commit": ""}
        bot = {"kind": "comment", "user": "owner", "user_type": "Bot",
               "body": f"tollgate approve {HEAD}", "state": "", "commit": ""}
        f = facts(changes={"pyproject.toml": 2}, approvals=[stale, stranger, bot], review_passed=True)
        self.assertEqual(rules(f), [4])

    def test_rule4_review_by_someone_else_counts(self):
        review = {"kind": "review", "user": "teammate", "user_type": "User",
                  "state": "APPROVED", "commit": HEAD, "body": "", "association": "COLLABORATOR"}
        outsider = dict(review, association="NONE")
        self.assertEqual(rules(facts(changes={"pyproject.toml": 2}, approvals=[outsider],
                                     review_passed=True)), [4])
        self.assertEqual(rules(facts(changes={"pyproject.toml": 2}, approvals=[review],
                                     review_passed=True)), [])
        own = dict(review, user="owner")
        self.assertEqual(rules(facts(changes={"pyproject.toml": 2}, approvals=[own],
                                     review_passed=True)), [4])

    def test_rule4_github_folder_always_fails(self):
        review = {"kind": "review", "user": "teammate", "user_type": "User",
                  "state": "APPROVED", "commit": HEAD, "body": ""}
        f = facts(changes={".github/workflows/x.yml": 3}, approvals=[review], review_passed=True)
        self.assertEqual(rules(f), [4])

    def test_rule4_replaced_test_needs_approval(self):
        f = facts()
        f.freeze.number = 2
        f.freeze.manifest["number"] = 2
        self.assertEqual(rules(f), [4])

    def test_rule5_failed_check(self):
        r = passing_results()
        r.checks.append(CheckResult("style", False))
        self.assertEqual(rules(facts(results=r)), [5])

    def test_rule5_locked_test_missing_skipped_or_failed(self):
        for status in ("failed", "skipped"):
            r = passing_results()
            r.tests[TESTS[0]]["status"] = status
            self.assertEqual(rules(facts(results=r)), [5], status)
        r = passing_results()
        del r.tests[TESTS[1]]
        self.assertEqual(rules(facts(results=r)), [5])

    def test_rule6_tier_3_needs_the_server_review(self):
        s = settings.parse('{"tiers": {"3": ["src/auth/**"]}}')
        self.assertEqual(rules(facts(settings=s, changes={"src/auth/a.py": 1})), [6])
        ok = facts(settings=s, changes={"src/auth/a.py": 1}, review_passed=True)
        self.assertEqual(rules(ok), [])


class FakeServer:
    def __init__(self, run, manifest=None):
        self._run = dict(run, title="tollgate freeze T-1", manifest=manifest)

    def run(self, run_id):
        return dict(self._run)

    def pull(self, pr):
        return {"author": "owner", "head": ""}

    def approvals(self, pr):
        return []

    def check_passed(self, sha, name):
        return None


class GateCollectTest(unittest.TestCase):
    """The gate on a real git repository with a real freeze tag."""

    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        r = self.repo
        r.write(".tollgate/settings.json", settings_text())
        r.commit("settings")
        r.git("checkout", "-q", "-b", "tg/T-1")
        r.write(mf.ticket_path("T-1"), TICKET)
        r.write("tests/test_t1.py", "# locked tests\n")
        self.frozen = r.commit("ticket and tests")
        m = {"ticket": "T-1", "commit": self.frozen, "run_id": 7, "tests": TESTS, "number": 1,
             "files": {mf.ticket_path("T-1"): "", "tests/test_t1.py": ""}}
        from action.gitio import fingerprint, show_bytes
        for p in m["files"]:
            m["files"][p] = fingerprint(show_bytes(str(r.path), self.frozen, p))
        r.tag("tg/freeze/T-1/1", "Freeze of T-1\n\n" + mf.dumps(m), self.frozen)
        self.manifest = m
        r.write("src/retry.py", "def retry():\n    return True\n")
        r.commit("build")

    def run_gate(self):
        f = gate.collect(str(self.repo.path), "main", "HEAD", "tg/T-1", passing_results(),
                         FakeServer(GOOD_RUN, self.manifest), pr=1)
        return gate.evaluate(f)

    def test_unchanged_locked_tests_pass(self):
        findings, level = self.run_gate()
        self.assertEqual(findings, [])
        self.assertEqual(level, 1)

    def test_a_weakened_locked_test_fails(self):
        self.repo.write("tests/test_t1.py", "# weakened\n")
        self.repo.commit("weaken")
        findings, _ = self.run_gate()
        self.assertIn(3, {f["rule"] for f in findings})

    def test_the_highest_freeze_number_counts(self):
        m = mf.loads(self.repo.git("for-each-ref", "--format=%(contents)", "refs/tags/tg/freeze/T-1/1"))
        m["tests"] = ["tests.test_t1::test_c1_other"]
        self.repo.tag("tg/freeze/T-1/2", mf.dumps(m), self.frozen)
        findings, _ = self.run_gate()
        messages = " ".join(f["message"] for f in findings)
        self.assertIn("test_c1_other", messages)
        self.assertIn("replaced", messages)


if __name__ == "__main__":
    unittest.main()
