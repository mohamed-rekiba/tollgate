"""Stage 3 proof: the task loop with fake roles, against a local server.

    python3 -m unittest tests.proof_stage3 -v
"""

import subprocess
import sys
import unittest

from driver.log import read
from tests.fakes import FAKE_ROLE, LocalServer, Sample, run_task

AI_ADVISOR = f"{sys.executable} {FAKE_ROLE} ok"
PLAN_ON = {"require_plan": True}


class TaskCase(unittest.TestCase):
    def start(self, advisor=(AI_ADVISOR,), **kw):
        kw.setdefault("extra", PLAN_ON)
        self.sample = Sample(advisor=advisor, **kw)
        self.addCleanup(self.sample.close)
        self.server = LocalServer(self.sample.bare)

    def task_events(self):
        return read(str(self.sample.project / ".tollgate/logs/task-demo.jsonl"))

    def ticket_events(self, tid):
        return read(str(self.sample.project / f".tollgate/logs/{tid}.jsonl"))

    def count(self, events, name):
        return sum(1 for e in events if e["event"] == name)

    def tags(self):
        return subprocess.run(["git", "tag"], cwd=self.sample.bare, capture_output=True,
                              text=True, check=True).stdout.split()


class TaskLoop(TaskCase):
    def test_a_task_goes_from_request_to_a_pull_request_for_each_ticket(self):
        self.start(builder="pass2")
        result = run_task(self.sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = self.task_events()
        for step in ("plan_written", "plan_review_clean", "advisor_decided", "plan_locked",
                     "reported"):
            self.assertIn(step, [e["event"] for e in events])
        self.assertIn("tg/plan/demo/1", self.tags())
        for tid in ("T-1", "T-2"):
            self.assertIn(f"tg/freeze/{tid}/1", self.tags())
            self.assertEqual(self.count(self.ticket_events(tid), "pr_opened"), 1)
        report = (self.sample.project / ".tollgate/reports/demo.md").read_text()
        self.assertIn("| T-1 | pull request open | 1 | 2 | 100 |", report)
        self.assertIn("| T-2 | pull request open |", report)
        self.assertIn("Plan: locked.", report)

    def test_the_gate_checks_the_plan_tag_run(self):
        """With require_plan on, each ticket's gate read the plan tag and its run."""
        self.start(builder="pass1", extra={**PLAN_ON, "tier1": {"max_files": 1, "max_lines": 1}})
        result = run_task(self.sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        passed = [e for e in self.ticket_events("T-1") if e["event"] == "attempt_passed"]
        self.assertEqual(passed[0]["tier"], 2)

    def test_a_plan_finding_is_fixed_and_the_next_round_is_clean(self):
        self.start(builder="pass1", reviewer="ok planfind=1")
        self.assertEqual(run_task(self.sample).returncode, 0)
        events = self.task_events()
        self.assertEqual(self.count(events, "plan_answered"), 1)
        clean = [e for e in events if e["event"] == "plan_review_clean"]
        self.assertEqual(clean[0]["round"], 2)

    def test_a_person_approves_the_plan_on_the_server(self):
        self.start(builder="pass1", advisor=("person",))
        self.assertEqual(run_task(self.sample).returncode, 3)
        questions = self.server.open_questions()
        self.assertEqual(len(questions), 1)
        self.assertIn("plan demo", next(iter(questions.values()))["title"])
        self.assertNotIn("tg/plan/demo/1", self.tags())
        self.server.answer(1, "tollgate decide approve")
        self.assertEqual(run_task(self.sample).returncode, 0)
        self.assertIn("tg/plan/demo/1", self.tags())
        self.assertEqual(self.count(self.task_events(), "plan_written"), 1)

    def test_a_plan_sent_back_is_not_locked(self):
        self.start(builder="pass1", advisor=(f"{AI_ADVISOR} plan_decision=send_back",))
        self.assertEqual(run_task(self.sample).returncode, 3)
        self.assertIn("plan_sent_back", [e["event"] for e in self.task_events()])
        self.assertNotIn("tg/plan/demo/1", self.tags())

    def test_the_task_cost_limit_stops_the_tickets(self):
        self.start(builder="same cost=2", reviewer="ok cost=2", task_usd=20)
        self.assertEqual(run_task(self.sample).returncode, 3)
        reasons = [e["reason"] for tid in ("T-1", "T-2") for e in self.ticket_events(tid)
                   if e["event"] == "stopped"]
        self.assertTrue(any("the task reached 20 USD" in r for r in reasons), reasons)
        report = (self.sample.project / ".tollgate/reports/demo.md").read_text()
        self.assertIn("Cost:", report)

    def test_a_finished_task_started_again_repeats_nothing(self):
        self.start(builder="pass1")
        self.assertEqual(run_task(self.sample).returncode, 0)
        before = {tid: len(self.ticket_events(tid)) for tid in ("T-1", "T-2")}
        self.assertEqual(run_task(self.sample).returncode, 0)
        events = self.task_events()
        self.assertEqual(self.count(events, "plan_written"), 1)
        self.assertEqual(self.count(events, "plan_locked"), 1)
        self.assertEqual({tid: len(self.ticket_events(tid)) for tid in ("T-1", "T-2")}, before)



if __name__ == "__main__":
    unittest.main()
