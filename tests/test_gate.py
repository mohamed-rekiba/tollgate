"""Tests for the gate: each of the six checks has a case that passes and a case that fails.

The lock and the plan lock are written with gate.state, in a state folder in a
temporary folder.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from gate import gate, state
from gate.checks import CheckResult, Results
from gate.gitio import fingerprint, show_bytes
from gate.manifest import ticket_path
from tests.helpers import TICKET, Repo, settings_text

TESTS = ["tests.test_t1::test_c1_retries", "tests.test_t1::test_c2_sent_once"]
TICKET_FILE = ticket_path("T-1")


def passing_results():
    return Results([CheckResult("tests", True)], {t: {"status": "passed", "file": ""} for t in TESTS})


class GateCase(unittest.TestCase):
    """A project with settings on main, a lock of T-1, a plan lock, and one try."""

    plan_required = True

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(os.environ, {"TOLLGATE_STATE": f"{tmp.name}/state",
                                           "TOLLGATE_KEYS": f"{tmp.name}/keys"})
        env.start()
        self.addCleanup(env.stop)
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.project = str(self.repo.path)
        r = self.repo
        r.write(".tollgate/settings.json", self.settings())
        self.base = r.commit("settings")
        r.git("checkout", "-q", "-b", "tg/T-1")
        r.write(TICKET_FILE, TICKET)
        r.write("tests/test_t1.py", "# locked tests\n")
        self.lock_commit = r.commit("lock T-1")
        self.lock = {"ticket": "T-1", "base_commit": self.base, "commit": self.lock_commit,
                     "manifest": {"files": self.prints(self.lock_commit, TICKET_FILE,
                                                       "tests/test_t1.py"),
                                  "tests": TESTS, "keeps_behavior": []},
                     "number": 1, "at": "2026-11-22T10:00:00Z"}
        self.write_lock(self.lock)
        self.plan = {"task": "retries", "commit": self.lock_commit,
                     "files": self.prints(self.lock_commit, TICKET_FILE),
                     "at": "2026-11-22T09:00:00Z"}
        self.write_plan(self.plan)
        self.build("def retry():\n    return True\n")

    def settings(self, **extra):
        base = json.loads(settings_text(require_plan=self.plan_required))
        base.update(extra)
        return json.dumps(base)

    def prints(self, commit, *paths):
        return {p: fingerprint(show_bytes(self.project, commit, p)) for p in paths}

    def write_lock(self, record):
        state.write_record(state.path(self.project, "locks", "T-1.json"), record)

    def write_plan(self, record):
        state.write_record(state.path(self.project, "plans", "retries.json"), record)

    def build(self, text, path="src/retry.py"):
        self.repo.write(path, text)
        self.repo.commit("try")

    def facts(self, results=None, review=None):
        return gate.collect(self.project, self.project, "main", "HEAD", "T-1",
                            results or passing_results(), review)

    def failed(self, facts=None):
        return sorted({f["check"] for f in gate.evaluate(facts or self.facts())})


class LockTest(GateCase):
    def test_a_lock_that_matches_passes(self):
        self.assertEqual(gate.evaluate(self.facts()), [])

    def test_a_lock_that_cannot_be_read_says_so(self):
        state.path(self.project, "locks", "T-1.json").unlink()
        lock = [f for f in gate.evaluate(self.facts()) if f["check"] == "lock"]
        self.assertIn("cannot be read", lock[0]["message"])

    def test_a_lock_whose_manifest_differs_from_its_commit_fails(self):
        self.lock["manifest"]["files"]["tests/test_t1.py"] = "sha256:" + "0" * 64
        self.write_lock(self.lock)
        self.assertIn("lock", self.failed())

    def test_a_lock_commit_that_adds_code_fails(self):
        self.repo.git("checkout", "-q", "main")
        self.repo.git("checkout", "-q", "-b", "tg/T-2")
        self.repo.write(TICKET_FILE, TICKET)
        self.repo.write("tests/test_t1.py", "# locked tests\n")
        self.repo.write("src/sneaky.py", "x = 1\n")
        commit = self.repo.commit("lock with code")
        self.write_lock(dict(self.lock, commit=commit))
        self.build("def retry():\n    return True\n")
        findings = gate.evaluate(self.facts())
        self.assertEqual({f["check"] for f in findings}, {"lock"})
        self.assertEqual([f["file"] for f in findings], ["src/sneaky.py"])

    def test_a_missing_lock_fails(self):
        state.path(self.project, "locks", "T-1.json").unlink()
        self.assertIn("lock", self.failed())


class PlanTest(GateCase):
    def setUp(self):
        super().setUp()
        self.build("x = 1\n" * 80, "src/big.py")  # tier 2

    def failed(self, facts=None):
        # A tier 2 try also needs a passed review; these tests check the plan alone.
        return super().failed(facts or self.facts(review=True))

    def test_a_plan_that_lists_the_ticket_passes(self):
        self.assertEqual(self.failed(), [])

    def test_a_plan_without_the_ticket_fails(self):
        self.write_plan(dict(self.plan, files={}))
        self.assertEqual(self.failed(), ["plan"])

    def test_a_missing_plan_lock_fails(self):
        state.path(self.project, "plans", "retries.json").unlink()
        self.assertEqual(self.failed(), ["plan"])

    def test_a_ticket_changed_after_the_plan_fails(self):
        self.write_plan(dict(self.plan, files={TICKET_FILE: "sha256:" + "0" * 64}))
        self.assertEqual(self.failed(), ["plan"])


class PlanTierOneTest(GateCase):
    def test_tier_1_needs_no_plan(self):
        state.path(self.project, "plans", "retries.json").unlink()
        f = self.facts()
        self.assertEqual(gate.tier_of(f)[0], 1)
        self.assertEqual(gate.evaluate(f), [])


class LockedFilesTest(GateCase):
    def test_unchanged_locked_files_pass(self):
        self.assertNotIn("locked_files", self.failed())

    def test_a_weakened_locked_test_fails_and_the_builder_can_fix_it(self):
        self.build("# weakened\n", "tests/test_t1.py")
        findings = gate.evaluate(self.facts())
        self.assertEqual([(f["check"], f["file"], f["fixable"]) for f in findings],
                         [("locked_files", "tests/test_t1.py", True)])


class ChainTest(GateCase):
    """A ticket in a task starts from the ready change before it, before that merges."""

    def test_a_later_ticket_may_not_change_an_earlier_ticket_s_locked_test(self):
        r = self.repo
        start = r.git("rev-parse", "HEAD").strip()
        r.git("checkout", "-q", "-b", "tg/T-2")
        r.write(".tollgate/tickets/T-2/ticket.md", TICKET.replace("id: T-1", "id: T-2"))
        r.write("tests/test_t2.py", "# locked tests of T-2\n")
        commit = r.commit("lock T-2")
        state.write_record(state.path(self.project, "locks", "T-2.json"), {"ticket": "T-2", "base_commit": start, "commit": commit,
                    "manifest": {"files": self.prints(commit, ".tollgate/tickets/T-2/ticket.md",
                                                      "tests/test_t2.py"),
                                 "tests": [], "keeps_behavior": []},
                    "number": 1, "at": "2026-11-22T10:00:00Z"})
        self.build("# weakened\n", "tests/test_t1.py")
        facts = gate.collect(self.project, self.project, "main", "HEAD", "T-2",
                             passing_results(), None, start=start)
        changed = [(f["check"], f["file"]) for f in gate.evaluate(facts)]
        self.assertIn(("locked_files", "tests/test_t1.py"), changed)


    T1_TESTS = ("def test_c1_retries():\n    assert True\n\n\n"
                "def test_c2_sent_once():\n    assert 1 == 1\n")

    def shared_file_chain(self, t2_file):
        """T-1 locked tests/test_t1.py; T-2 adds its own test to the same file and locks it."""
        r = self.repo
        r.git("checkout", "-q", "tg/T-1")
        r.write("tests/test_t1.py", self.T1_TESTS)
        first = r.commit("lock T-1 again")
        self.write_lock(dict(self.lock, commit=first, manifest=dict(
            self.lock["manifest"], files=self.prints(first, TICKET_FILE, "tests/test_t1.py"))))
        start = r.git("rev-parse", "HEAD").strip()
        r.git("checkout", "-q", "-b", "tg/T-2")
        r.write(".tollgate/tickets/T-2/ticket.md", TICKET.replace("id: T-1", "id: T-2"))
        r.write("tests/test_t1.py", t2_file)
        commit = r.commit("lock T-2")
        state.write_record(state.path(self.project, "locks", "T-2.json"), {"ticket": "T-2", "base_commit": start, "commit": commit,
                    "manifest": {"files": self.prints(commit, ".tollgate/tickets/T-2/ticket.md",
                                                      "tests/test_t1.py"),
                                 "tests": [], "keeps_behavior": []},
                    "number": 1, "at": "2026-11-22T10:00:00Z"})
        self.build("def retry():\n    return 2\n")
        facts = gate.collect(self.project, self.project, "main", "HEAD", "T-2",
                             passing_results(), None, start=start)
        return [(f["check"], f["file"]) for f in gate.evaluate(facts)]

    def test_a_later_ticket_may_add_a_test_to_a_file_an_earlier_ticket_locked(self):
        added = self.T1_TESTS + "\n\ndef test_c1_divide_by_zero():\n    assert 2 == 2\n"
        self.assertNotIn(("locked_files", "tests/test_t1.py"), self.shared_file_chain(added))

    def test_a_later_ticket_may_not_change_or_drop_an_earlier_ticket_s_test_in_it(self):
        changed = self.T1_TESTS.replace("assert 1 == 1", "assert True")
        dropped = self.T1_TESTS.split("\n\n\ndef test_c2")[0] + "\n"
        for text in (changed, dropped):
            with self.subTest(text=text):
                self.setUp()
                self.assertIn(("locked_files", "tests/test_t1.py"), self.shared_file_chain(text))


class TierTest(GateCase):
    def test_a_small_change_is_tier_1_and_locked_files_do_not_count(self):
        self.assertEqual(gate.tier_of(self.facts())[0], 1)

    def test_a_harness_change_is_tier_4_and_needs_the_review(self):
        self.build("[pytest]\n", "pytest.ini")
        f = self.facts()
        self.assertEqual(gate.tier_of(f)[0], 4)
        self.assertIn("review", self.failed(f))


class TestsTest(GateCase):
    def test_passing_checks_and_locked_tests_pass(self):
        self.assertNotIn("tests", self.failed())

    def test_a_failed_check_fails_and_the_builder_can_fix_it(self):
        r = passing_results()
        r.checks.append(CheckResult("style", False))
        findings = gate.evaluate(self.facts(r))
        self.assertEqual([(f["check"], f["fixable"]) for f in findings], [("tests", True)])

    def test_a_locked_test_failed_skipped_or_missing_fails(self):
        for status in ("failed", "skipped", None):
            r = passing_results()
            if status:
                r.tests[TESTS[0]]["status"] = status
            else:
                del r.tests[TESTS[0]]
            self.assertEqual(self.failed(self.facts(r)), ["tests"], status)


class ReviewTest(GateCase):
    plan_required = False

    def setUp(self):
        super().setUp()
        self.repo.git("checkout", "-q", "main")
        self.repo.write(".tollgate/settings.json",
                        self.settings(tiers={"3": ["src/auth/**"]}))
        self.repo.commit("tier 3 rule")
        self.repo.git("checkout", "-q", "tg/T-1")
        self.build("x = 1\n", "src/auth/login.py")

    def test_tier_3_passes_with_a_passed_review(self):
        self.assertEqual(self.failed(self.facts(review=True)), [])

    def test_tier_3_fails_without_a_passed_review(self):
        for verdict in (None, False):
            findings = gate.evaluate(self.facts(review=verdict))
            self.assertEqual([(f["check"], f["fixable"]) for f in findings],
                             [("review", False)], verdict)


class Tier2ReviewTest(GateCase):
    plan_required = False

    def setUp(self):
        super().setUp()
        self.repo.git("checkout", "-q", "main")
        self.repo.write(".tollgate/settings.json",
                        self.settings(tier1={"max_files": 0, "max_lines": 0}))
        self.repo.commit("every change is tier 2")
        self.repo.git("checkout", "-q", "tg/T-1")
        self.build("x = 1\n", "src/app.py")

    def test_tier_2_needs_a_passed_review(self):
        self.assertEqual(gate.tier_of(self.facts(review=True))[0], 2)
        self.assertEqual(self.failed(self.facts(review=True)), [])
        for verdict in (None, False):
            self.assertEqual(self.failed(self.facts(review=verdict)), ["review"], verdict)


class PassRecordTest(GateCase):
    def test_a_passed_try_gets_a_record_in_the_contract_format(self):
        f = self.facts()
        record = gate.pass_record(f, 85, at="2026-11-22T11:00:00Z")
        self.assertEqual(sorted(record), ["at", "base_commit", "checks", "commit", "lock_sha256",
                                          "score", "ticket", "tier"])
        self.assertEqual(record["base_commit"], self.base)
        self.assertEqual(record["commit"], f.head_sha)
        self.assertEqual((record["ticket"], record["tier"], record["score"]), ("T-1", 1, 85))
        self.assertEqual(record["checks"], {name: True for name in gate.CHECKS})
        lock_bytes = state.path(self.project, "locks", "T-1.json").read_bytes()
        import hashlib
        self.assertEqual(record["lock_sha256"], hashlib.sha256(lock_bytes).hexdigest())

    def test_a_failed_try_or_a_low_score_gets_no_record(self):
        with self.assertRaisesRegex(gate.GateError, "below 70"):
            gate.pass_record(self.facts(), 69)
        r = passing_results()
        r.checks.append(CheckResult("style", False))
        with self.assertRaisesRegex(gate.GateError, "finding"):
            gate.pass_record(self.facts(r), 100)


class CommandLineTest(GateCase):
    def test_a_malformed_results_file_ends_with_2(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write('{"unexpected": true}')
            f.flush()
            self.assertEqual(gate.main(["--ticket", "T-1", "--results", f.name]), 2)

    def test_a_passing_try_ends_with_0(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write(passing_results().to_json())
            f.flush()
            argv = ["--project", self.project, "--repo", self.project, "--ticket", "T-1",
                    "--results", f.name]
            with mock.patch("sys.stdout"):
                self.assertEqual(gate.main(argv), 0)


if __name__ == "__main__":
    unittest.main()
