"""Stage 3 proof: a task, with a plan review and several tickets, with the real store.

    python3 -m unittest tests.proof_stage3 -v

The fake planner writes plan demo with two tickets: demo-1 adds shout, demo-2
adds whisper. Each task runs as its own process, as the task skill starts it.
"""

import unittest
from pathlib import Path

from gate import sign, state
from tests.proof_common import ROLE, Project, events, tries

AI_ADVISOR = f"{ROLE} ok"
TICKETS = ("demo-1", "demo-2")


class TaskCase(unittest.TestCase):
    def start(self, advisor=(AI_ADVISOR,), **settings_args) -> Project:
        settings_args.setdefault("require_plan", True)
        self.p = Project(ticket=False, advisor=advisor, **settings_args)
        self.addCleanup(self.p.close)
        return self.p

    def task_log(self):
        return self.p.log_of("task-demo")

    def plan_lock(self) -> Path:
        return state.path(str(self.p.project), "plans", "demo.json")


class TaskLoop(TaskCase):
    def test_a_task_reviews_its_plan_locks_it_and_merges_each_ticket(self):
        p = self.start(builder="pass2", reviewer="ok planfind=1", auto_merge=True)
        result = p.task()
        self.assertEqual(result.returncode, 0, result.stderr)
        log = self.task_log()
        # Round 1 finds a problem, the planner answers it, and round 2 is clean.
        self.assertEqual(events(log).count("plan_answered"), 1)
        self.assertEqual([e["round"] for e in log if e["event"] == "plan_review_clean"], [2])
        self.assertEqual([e["event"] for e in log if e["event"] in (
            "plan_review_done", "advisor_decided", "plan_locked", "reported")],
            ["plan_review_done", "advisor_decided", "plan_locked", "reported"])
        signers = [sign.ensure_key()]
        plan = sign.read(self.plan_lock(), "tollgate-plan", signers)
        self.assertEqual(plan["task"], "demo")
        self.assertIn(".tollgate/tickets/demo-1/ticket.md", plan["files"])
        for tid in TICKETS:
            ticket_log = p.log_of(tid)
            self.assertEqual(events(ticket_log)[-1], "merged", tid)
            self.assertTrue(p.main_has(tries(ticket_log)[-1]["commit"]), tid)
        app = (p.project / "app.py").read_text()
        self.assertIn("def shout(", app)
        self.assertIn("def whisper(", app)
        report = state.path(str(p.project), "reports", "demo.md").read_text()
        self.assertIn("- demo-1: merged.", report)
        self.assertIn("- demo-2: merged.", report)
        self.assertIn("Plan: locked.", report)
        # The driver writes nothing in the project but what merged.
        self.assertFalse((p.project / ".tollgate" / "plans").exists())

    def test_with_require_plan_a_ticket_with_no_plan_lock_stops(self):
        # Tier 2, so the gate checks the plan lock. Ticket T-1 names plan demo, never locked.
        self.p = p = Project(builder="pass1", advisor=(), require_plan=True,
                             tier1={"max_files": 1, "max_lines": 1})
        self.addCleanup(p.close)
        self.assertEqual(p.drive().returncode, 3)
        stopped = [e["reason"] for e in p.log_of("T-1") if e["event"] == "stopped"]
        self.assertIn("the plan lock of demo does not verify", stopped[0])
        self.assertNotIn("try_passed", events(p.log_of("T-1")))

    def test_a_task_with_tier_2_tickets_passes_the_plan_check(self):
        p = self.start(builder="pass1", tier1={"max_files": 1, "max_lines": 1})
        result = p.task()
        self.assertEqual(result.returncode, 0, result.stderr)
        for tid in TICKETS:
            passed = [e for e in p.log_of(tid) if e["event"] == "try_passed"]
            self.assertEqual(passed[0]["tier"], 2, tid)
            self.assertEqual(events(p.log_of(tid))[-1], "waiting_for_merge", tid)

    def test_a_finished_task_started_again_repeats_nothing(self):
        p = self.start(builder="pass1")
        self.assertEqual(p.task().returncode, 0)
        before = {tid: len(p.log_of(tid)) for tid in TICKETS}
        self.assertEqual(p.task().returncode, 0)
        log = self.task_log()
        self.assertEqual(events(log).count("plan_written"), 1)
        self.assertEqual(events(log).count("plan_locked"), 1)
        self.assertEqual({tid: len(p.log_of(tid)) for tid in TICKETS}, before)


class PlanApproval(TaskCase):
    def test_you_approve_the_plan_through_the_store(self):
        p = self.start(builder="pass1", advisor=("person",))
        self.assertEqual(p.task().returncode, 3)
        questions = p.store.open_questions()
        self.assertEqual(list(questions), [1])
        self.assertIn("plan demo", questions[1]["title"])
        self.assertEqual(questions[1]["options"], ["approve", "send_back"])
        self.assertFalse(self.plan_lock().exists())
        answered = p.run("setup.inbox", "--project", ".", "answer", "1", "approve")
        self.assertEqual(answered.returncode, 0, answered.stderr)
        result = p.task()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.plan_lock().exists())
        self.assertEqual(events(self.task_log()).count("plan_written"), 1)
        decided = [e for e in self.task_log() if e["event"] == "advisor_decided"]
        self.assertEqual([(d["by"], d["decision"]) for d in decided], [("person", "approve")])

    def test_a_plan_sent_back_is_not_locked(self):
        p = self.start(builder="pass1", advisor=(f"{AI_ADVISOR} plan_decision=send_back",))
        self.assertEqual(p.task().returncode, 3)
        self.assertIn("plan_sent_back", events(self.task_log()))
        self.assertFalse(self.plan_lock().exists())
        for tid in TICKETS:
            self.assertEqual(p.log_of(tid), [])

    def test_a_ticket_that_waits_for_you_does_not_stop_the_others(self):
        p = self.start(builder="same", advisor=(AI_ADVISOR, "person"))
        self.assertEqual(p.task().returncode, 3)
        for tid in TICKETS:
            self.assertIn(events(p.log_of(tid))[-1], ("waiting_for_advisor", "parked"), tid)
        report = state.path(str(p.project), "reports", "demo.md").read_text()
        self.assertIn("Still to do", report)


if __name__ == "__main__":
    unittest.main()
