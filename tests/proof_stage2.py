"""Stage 2 proof: the driver with fake roles, against a local server.

    python3 -m unittest tests.proof_stage2 -v

Each case runs the driver as its own process on a fresh sample project.
"""

import json
import subprocess
import sys
import unittest

from driver.log import read
from tests.fakes import FAKE_ROLE, LocalServer, Sample, run_driver


class Case(unittest.TestCase):
    def start(self, **settings_args):
        self.sample = Sample(**settings_args)
        self.addCleanup(self.sample.close)

    def events(self):
        return read(str(self.sample.project / ".tollgate/logs/T-1.jsonl"))

    def count(self, name):
        return sum(1 for e in self.events() if e["event"] == name)

    def stopped(self):
        return [e["reason"] for e in self.events() if e["event"] == "stopped"]


class BuildOrderCases(Case):
    """The four cases from the build order, and the second driver."""

    def test_a_builder_that_passes_on_attempt_2_ends_with_a_pull_request(self):
        self.start(builder="pass2")
        result = run_driver(self.sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.count("attempt_failed"), 1)
        self.assertEqual(self.count("attempt_passed"), 1)
        self.assertEqual(self.count("pr_opened"), 1)
        steps = [e["event"] for e in self.events()]
        for step in ("tests_written", "tests_reviewed", "frozen", "attempt_started",
                     "pr_opened", "waiting_for_merge"):
            self.assertIn(step, steps)

    def test_the_same_check_failing_twice_stops_after_2_attempts(self):
        self.start(builder="same")
        result = run_driver(self.sample)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.count("attempt_failed"), 2)
        self.assertIn("the same checks failed", self.stopped()[0])
        self.assertEqual(self.count("waiting_for_advisor"), 1)

    def test_a_different_check_each_time_stops_after_3_attempts(self):
        self.start(builder="different")
        result = run_driver(self.sample)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.count("attempt_failed"), 3)
        self.assertIn("used 3 attempts", self.stopped()[0])

    def test_a_killed_driver_started_again_repeats_no_finished_step(self):
        self.start(builder="pass2")
        marker = self.sample.env_home / "died"
        self.sample = self._restart_with(f"pass2 die_once={marker}")
        first = run_driver(self.sample)
        self.assertEqual(first.returncode, -9, first.stderr)
        self.assertEqual(self.count("frozen"), 1)
        self.assertEqual(self.count("attempt_failed") + self.count("attempt_passed"), 0)
        second = run_driver(self.sample)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.count("tests_written"), 1)
        self.assertEqual(self.count("frozen"), 1)
        self.assertEqual(self.count("pr_opened"), 1)

    def _restart_with(self, builder):
        sample = Sample(builder=builder)
        self.addCleanup(sample.close)
        return sample

    def test_a_second_driver_for_the_same_ticket_refuses_to_start(self):
        self.start(builder="pass2")
        lock = self.sample.project / ".tollgate/run/T-1.lock"
        lock.parent.mkdir(parents=True)
        holder = subprocess.Popen(["sleep", "60"])
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        lock.write_text(str(holder.pid))
        result = run_driver(self.sample)
        self.assertEqual(result.returncode, 4)
        self.assertIn("another driver holds", result.stderr)
        self.assertEqual(self.events(), [])


class StopRules(Case):
    def test_an_attempt_past_its_time_stops(self):
        self.start(builder="slow", attempt_minutes=0.05)
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertIn("ran for 0.05 minutes", self.stopped()[0])

    def test_the_ticket_cost_stops(self):
        self.start(builder="different cost=6", reviewer="ok cost=6", ticket_usd=20)
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertIn("the ticket cost", self.stopped()[0])
        self.assertEqual(self.count("attempt_failed"), 2)

    def test_the_task_cost_stops(self):
        self.start(builder="pass2", task_usd=5)
        other = self.sample.project / ".tollgate/logs/T-0.jsonl"
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps({"event": "x", "task": "demo", "cost_usd": 6}) + "\n")
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertIn("the task reached 5 USD", self.stopped()[0])


class PersonAdvisor(Case):
    def test_a_person_answers_on_the_server_and_the_driver_goes_on(self):
        self.start(builder="same")
        server = LocalServer(self.sample.bare)
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertEqual(list(server.open_questions()), ["1"])
        self.assertIn("tollgate decide retry", server.open_questions()["1"]["body"])
        # A user who is not an approver, and a bot, do not count.
        server.answer(1, "tollgate decide retry", user="stranger")
        server.answer(1, "tollgate decide retry", user="owner", user_type="Bot")
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertEqual(self.count("still_waiting"), 1)
        server.answer(1, "tollgate decide retry look at shout\n\nfooter")
        self.assertEqual(run_driver(self.sample).returncode, 3)
        decided = [e for e in self.events() if e["event"] == "advisor_decided"]
        self.assertEqual([(d["by"], d["decision"], d["hint"]) for d in decided],
                         [("person", "retry", "look at shout")])
        self.assertEqual(self.count("attempt_failed"), 3)
        self.assertEqual(list(server.open_questions()), ["2"])


class StrongerBuilder(Case):
    def test_a_stronger_decision_runs_the_stronger_builder(self):
        role = f"{sys.executable} {FAKE_ROLE}"
        self.start(builder="same", extra={"ai": {
            "builder": f"{role} same", "reviewer": f"{role} ok",
            "advisor": [f"{role} ok decision=stronger"], "stronger_builder": f"{role} pass1"}})
        self.assertEqual(run_driver(self.sample).returncode, 0)
        self.assertEqual(self.count("attempt_failed"), 2)
        self.assertEqual(self.count("attempt_passed"), 1)
        self.assertEqual(self.count("pr_opened"), 1)


class Guards(Case):
    def test_a_blocking_change_finding_on_tier_2_fails_the_attempt(self):
        self.start(builder="pass2", reviewer="ok block=change",
                   extra={"tier1": {"max_files": 1, "max_lines": 1}})
        self.assertEqual(run_driver(self.sample).returncode, 3)
        failed = [e for e in self.events() if e["event"] == "attempt_failed" and e["score"] >= 0]
        self.assertTrue(failed)
        self.assertEqual(failed[-1]["tier"], 2)
        self.assertEqual(failed[-1]["findings"][0]["lens"], "change")
        self.assertEqual(self.count("pr_opened"), 0)

    def test_a_change_under_github_is_never_pushed(self):
        self.start(builder="github")
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertIn("rule the builder cannot fix", self.stopped()[0])
        branch = subprocess.run(["git", "ls-tree", "-r", "--name-only", "tg/T-1"],
                                cwd=self.sample.bare, capture_output=True, text=True,
                                check=False).stdout
        self.assertNotIn(".github", branch)

    def test_an_ai_advisor_decides_at_most_twice(self):
        advisor = f"{sys.executable} {FAKE_ROLE} ok decision=retry"
        self.start(builder="same", advisor=(advisor,))
        self.assertEqual(run_driver(self.sample).returncode, 3)
        self.assertEqual(self.count("advisor_decided"), 2)
        self.assertEqual(self.count("parked"), 1)

    def test_a_checklist_pass_on_a_missing_line_lowers_the_score(self):
        self.start(builder="pass2", reviewer="ok badline")
        self.assertEqual(run_driver(self.sample).returncode, 3)
        scores = [e["score"] for e in self.events() if e["event"] == "attempt_failed"
                  and e["score"] >= 0]
        self.assertTrue(scores)
        self.assertTrue(all(s == 67 for s in scores))


if __name__ == "__main__":
    unittest.main()
