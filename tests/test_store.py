"""Tests for the store: each method has a passing and a failing case."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gate import freeze, sign, state
from gate import manifest as mf
from gate import plan as pl
from gate.store import Store, StoreError
from tests.fakes import RUN_TESTS, TICKET
from tests.helpers import Repo
from tests.test_plan_review import PLAN

TESTS = '''import unittest
import app


class T(unittest.TestCase):
    def test_c1_shout(self):
        self.assertEqual(app.shout("ann"), "HELLO ANN")

    def test_c2_greet(self):
        self.assertEqual(app.greet("ann"), "hello ann")
'''


class StoreCase(unittest.TestCase):
    """A project on main with signers, a state folder, and a key, all temporary."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, folder in (("TOLLGATE_STATE", "state"), ("TOLLGATE_KEYS", "keys")):
            old = os.environ.get(name)
            os.environ[name] = str(Path(self.tmp.name, folder))
            self.addCleanup(lambda n=name, o=old: os.environ.pop(n) if o is None
                            else os.environ.__setitem__(n, o))
        self.pub = sign.ensure_key()
        self.owner = Path(self.tmp.name, "owner")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.owner)],
                       check=True)
        self.owner_pub = Path(f"{self.owner}.pub").read_text().strip()
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        r = self.repo
        r.write("app.py", 'def greet(name):\n    return f"hello {name}"\n')
        r.write("run_tests.py", RUN_TESTS)
        r.write("tests/__init__.py", "")
        r.write(".gitignore", "report.xml\n__pycache__/\n")
        self.write_settings([self.pub])
        self.main = r.commit("main")
        self.store = Store(str(r.path))

    def write_settings(self, signers, **extra):
        self.repo.write(".tollgate/settings.json", json.dumps({
            "checks": {"tests": {"run": f"{sys.executable} run_tests.py", "report": "report.xml"}},
            "harness": ["run_tests.py"], "require_plan": False, "signers": signers,
            "owners": extra.pop("owners", [self.owner_pub]), **extra}))

    def ticket_branch(self, tests=TESTS, ticket=TICKET):
        r = self.repo
        r.git("checkout", "-q", "-b", "tg/T-1", "main")
        r.write(mf.ticket_path("T-1"), ticket)
        r.write("tests/test_t1.py", tests)
        commit = r.commit("test(T-1): the ticket and its locked tests")
        r.git("checkout", "-q", "main")
        return commit

    def change(self, path="app.py", text='def greet(name):\n    return f"hello {name}"\n\n'
               'def shout(name):\n    return greet(name).upper()\n'):
        r = self.repo
        r.git("checkout", "-q", "-B", "tg/T-1-build", "main")
        r.write(path, text)
        commit = r.commit("feat(T-1): shout")
        r.git("checkout", "-q", "main")
        return commit

    def pass_record(self, commit, tier=2, ticket="T-1"):
        return {"commit": commit, "ticket": ticket, "tier": tier,
                "lock_sha256": freeze.lock_sha256(str(self.repo.path), ticket) if ticket else None,
                "checks": {"tests": True}, "score": 100}

    def approve(self, commit, key=None):
        path = state.path(str(self.repo.path), "approvals", f"{commit}.json")
        sign.write(path, {"commit": commit, "ticket": "T-1", "approver": "owner",
                          "at": "2026-11-22T00:00:00Z"}, "tollgate-approval",
                   key=str(key or self.owner))


class FreezeTest(StoreCase):
    def test_writes_a_signed_lock(self):
        commit = self.ticket_branch()
        path = Path(self.store.freeze("T-1"))
        lock = sign.read(path, "tollgate-lock", [self.pub])
        self.assertEqual((lock["commit"], lock["base_commit"], lock["number"]),
                         (commit, self.main, 1))
        self.assertEqual(lock["manifest"]["tests"],
                         ["tests.test_t1::test_c1_shout", "tests.test_t1::test_c2_greet"])
        self.assertEqual(lock["manifest"]["keeps_behavior"], ["tests.test_t1::test_c2_greet"])

    def test_refuses_a_test_that_passes_before_the_build(self):
        self.ticket_branch(tests=TESTS.replace('app.shout("ann")', '"HELLO ANN"'))
        with self.assertRaisesRegex(StoreError, "passed before the build"):
            self.store.freeze("T-1")

    def test_runs_with_mains_harness(self):
        # The ticket's commit weakens the harness so that every test passes; main's copy wins.
        self.repo.git("checkout", "-q", "-b", "tg/T-1", "main")
        self.repo.write(mf.ticket_path("T-1"), TICKET)
        self.repo.write("tests/test_t1.py", TESTS)
        self.repo.write("run_tests.py", 'open("report.xml", "w").write("<testsuites/>")\n')
        self.repo.commit("weak harness")
        self.repo.git("checkout", "-q", "main")
        self.assertTrue(self.store.freeze("T-1"))

    def test_a_second_lock_replaces_the_first_and_a_third_is_refused(self):
        self.ticket_branch()
        first = Path(self.store.freeze("T-1")).read_bytes()
        second = sign.read(Path(self.store.freeze("T-1")), "tollgate-lock", [self.pub])
        self.assertEqual(second["number"], 2)
        self.assertEqual(freeze.replaced_path(str(self.repo.path), "T-1").read_bytes(), first)
        with self.assertRaisesRegex(StoreError, "already has 2 freezes"):
            self.store.freeze("T-1")

    def test_refuses_a_ticket_that_differs_from_the_locked_plan(self):
        self.ticket_branch(ticket=TICKET.replace("plan: demo", "plan: retries"))
        r = self.repo
        r.git("checkout", "-q", "-b", "tg-plan/retries", "main")
        r.write(pl.plan_path("retries"), PLAN)
        r.write(mf.ticket_path("T-1"), TICKET.replace("plan: demo", "plan: retries")
                .replace("There is no shout.", "There is no shout at all."))
        r.commit("the plan")
        r.git("checkout", "-q", "main")
        self.store.lock_plan("retries")
        with self.assertRaisesRegex(StoreError, "differs from the approved ticket"):
            self.store.freeze("T-1")

    def test_refuses_when_this_key_is_not_a_signer(self):
        self.write_settings([self.owner_pub])
        self.repo.commit("signers")
        self.ticket_branch()
        with self.assertRaisesRegex(StoreError, "not in signers"):
            self.store.freeze("T-1")


class LockPlanTest(StoreCase):
    def plan_branch(self, with_ticket=True):
        r = self.repo
        r.git("checkout", "-q", "-b", "tg-plan/retries", "main")
        r.write(pl.plan_path("retries"), PLAN)
        if with_ticket:
            r.write(mf.ticket_path("T-1"), TICKET.replace("plan: demo", "plan: retries"))
        commit = r.commit("the plan")
        r.git("checkout", "-q", "main")
        return commit

    def test_signs_the_plan_and_its_tickets(self):
        commit = self.plan_branch()
        found = sign.read(Path(self.store.lock_plan("retries")), "tollgate-plan", [self.pub])
        self.assertEqual(found["commit"], commit)
        self.assertEqual(sorted(found["files"]), sorted([mf.ticket_path("T-1"), pl.plan_path("retries")]))
        self.assertEqual(self.repo.git("tag", "--list"), "")

    def test_refuses_a_missing_ticket_and_a_second_lock(self):
        self.plan_branch(with_ticket=False)
        with self.assertRaisesRegex(StoreError, "T-1 has no file"):
            self.store.lock_plan("retries")
        self.repo.git("branch", "-D", "tg-plan/retries")
        self.plan_branch()
        self.store.lock_plan("retries")
        with self.assertRaisesRegex(StoreError, "already locked"):
            self.store.lock_plan("retries")


class QuestionTest(StoreCase):
    def test_ask_answer_close(self):
        n = self.store.ask("T-1 waits", "Pick one.", options=["retry", "stop"])
        self.assertEqual(list(self.store.open_questions()), [n])
        self.store.answer(n, "tollgate decide retry keep it short")
        self.assertEqual(self.store.open_questions(), {})
        self.assertEqual(self.store.question(n)["answer"]["hint"], "keep it short")
        self.store.close_question(n)
        self.assertEqual(self.store.question(n)["answer"]["decision"], "retry")
        self.assertEqual(self.store.ask("next", ""), n + 1)

    def test_refuses_an_answer_outside_the_options_and_a_closed_question(self):
        n = self.store.ask("T-1 waits", "Pick one.", options=["retry", "stop"])
        with self.assertRaisesRegex(StoreError, "not one of"):
            self.store.answer(n, "merge")
        self.assertIn(n, self.store.open_questions())
        self.store.close_question(n)
        with self.assertRaisesRegex(StoreError, "not open"):
            self.store.answer(n, "retry")
        with self.assertRaisesRegex(StoreError, "not open"):
            self.store.close_question(n)


class PassTest(StoreCase):
    def test_a_recorded_pass_reads_back(self):
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.assertEqual(self.store.passed(commit)["score"], 100)

    def test_a_changed_or_missing_pass_is_none(self):
        commit = self.change()
        self.assertIsNone(self.store.passed(commit))
        self.store.record_pass(commit, self.pass_record(commit))
        path = state.path(str(self.repo.path), "passes", f"{commit}.json")
        path.write_bytes(path.read_bytes().replace(b'"tier": 2', b'"tier": 1'))
        self.assertIsNone(self.store.passed(commit))

    def test_a_signer_only_in_the_change_does_not_count(self):
        # The change lists its own key in signers; verification reads main.
        commit = self.change(".tollgate/settings.json", json.dumps({"signers": [self.pub]}))
        self.write_settings([self.owner_pub])
        self.repo.commit("signers")
        sign.write(state.path(str(self.repo.path), "passes", f"{commit}.json"),
                   dict(self.pass_record(commit), at="x"), "tollgate-pass")
        self.assertIsNone(self.store.passed(commit))

    def test_record_pass_refuses_a_bad_record(self):
        commit = self.change()
        with self.assertRaisesRegex(StoreError, "keys"):
            self.store.record_pass(commit, {"commit": commit})
        with self.assertRaisesRegex(StoreError, "names"):
            self.store.record_pass(commit, self.pass_record("a" * 40))


class ApprovalTest(StoreCase):
    def test_an_owner_approval_verifies(self):
        commit = self.change()
        self.approve(commit)
        self.assertEqual([a["approver"] for a in self.store.approvals(commit)], ["owner"])

    def test_an_approval_from_another_key_does_not(self):
        commit = self.change()
        other = Path(self.tmp.name, "other")
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)],
                       check=True)
        self.approve(commit, key=other)
        self.assertEqual(self.store.approvals(commit), [])


    def test_the_machine_key_cannot_approve(self):
        # The driver can use the machine key, so an approval must come from an owner key.
        commit = self.change()
        self.approve(commit, key=sign.machine_key())
        self.assertEqual(self.store.approvals(commit), [])


class ReadyTest(StoreCase):
    def test_marks_a_passed_branch(self):
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.store.ready("tg/T-1-build", "T-1")
        path = state.path(str(self.repo.path), "passes", "ready", "T-1.json")
        self.assertEqual(sign.read(path, "tollgate-pass", [self.pub])["commit"], commit)

    def test_refuses_a_branch_with_no_pass(self):
        self.change()
        with self.assertRaisesRegex(StoreError, "no pass record"):
            self.store.ready("tg/T-1-build", "T-1")


class MergeTest(StoreCase):
    def test_merges_a_passed_change_with_a_merge_commit(self):
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.store.ready("tg/T-1-build", "T-1")
        merged = self.store.merge(commit)
        parents = self.repo.git("rev-list", "--parents", "-n", "1", merged).split()[1:]
        self.assertEqual(parents, [self.main, commit])
        self.assertFalse(state.path(str(self.repo.path), "passes", "ready", "T-1.json").exists())

    def test_the_merge_commit_passes_the_commit_message_check(self):
        # A project set up by /tollgate:init runs this check on the store's merge too.
        from setup import check_commit_msg
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.store.ready("tg/T-1-build", "T-1")
        merged = self.store.merge(commit)
        message = self.repo.git("log", "-1", "--format=%B", merged)
        self.assertEqual(check_commit_msg.problems(message, in_merge=True), [])

    def test_refuses_with_no_pass(self):
        commit = self.change()
        with self.assertRaisesRegex(StoreError, "no verified pass record"):
            self.store.merge(commit)

    def test_tier_3_needs_an_approval(self):
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit, tier=3))
        with self.assertRaisesRegex(StoreError, "needs your signed approval"):
            self.store.merge(commit)
        self.approve(commit)
        self.assertTrue(self.store.merge(commit))

    def test_a_change_made_by_hand_merges_on_an_owner_approval(self):
        commit = self.change()
        with self.assertRaisesRegex(StoreError, "no approval of a change made by hand"):
            self.store.merge(commit)
        sign.write(state.path(str(self.repo.path), "approvals", f"{commit}.json"),
                   {"commit": commit, "ticket": "", "approver": "owner",
                    "at": "2026-11-22T00:00:00Z"}, "tollgate-approval", key=str(self.owner))
        self.assertTrue(self.store.merge(commit))

    def test_refuses_a_pass_for_an_old_lock(self):
        self.ticket_branch()
        self.store.freeze("T-1")
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.store.freeze("T-1")
        with self.assertRaisesRegex(StoreError, "not for the current lock"):
            self.store.merge(commit)

    def test_refuses_a_main_worktree_with_changes(self):
        commit = self.change()
        self.store.record_pass(commit, self.pass_record(commit))
        self.repo.write("app.py", "changed = True\n")
        with self.assertRaisesRegex(StoreError, "has changes"):
            self.store.merge(commit)

    def test_an_untracked_file_the_change_adds_with_the_same_bytes_is_removed(self):
        # You wrote the ticket on main before the task; the change adds the same file.
        commit = self.change(path=mf.ticket_path("T-1"), text=TICKET)
        self.store.record_pass(commit, self.pass_record(commit))
        self.repo.write(mf.ticket_path("T-1"), TICKET)
        self.assertTrue(self.store.merge(commit))
        self.assertEqual(Path(self.repo.path, mf.ticket_path("T-1")).read_text(), TICKET)
        self.assertEqual(self.repo.git("status", "--porcelain").strip(), "")

    def test_an_untracked_file_the_change_adds_with_other_bytes_is_refused(self):
        commit = self.change(path=mf.ticket_path("T-1"), text=TICKET)
        self.store.record_pass(commit, self.pass_record(commit))
        self.repo.write(mf.ticket_path("T-1"), "my own notes\n")
        with self.assertRaisesRegex(StoreError, "untracked files .* other content"):
            self.store.merge(commit)
        self.assertEqual(Path(self.repo.path, mf.ticket_path("T-1")).read_text(),
                         "my own notes\n")
        self.assertNotIn("T-1", self.repo.git("log", "--oneline", "main"))


if __name__ == "__main__":
    unittest.main()
