"""Stage 2 proof: one ticket, from the lock to the merge, with the real store.

    python3 -m unittest tests.proof_stage2 -v

Each case runs the driver as its own process on a fresh sample project. The
ticket T-1 asks for shout. The fake builder's mode decides how each try goes.
"""

import json
import subprocess
import unittest

from gate import state
from tests.proof_common import ROLE, Project, events, tries


class Case(unittest.TestCase):
    def start(self, **settings_args) -> Project:
        self.p = Project(**settings_args)
        self.addCleanup(self.p.close)
        return self.p

    def log(self):
        return self.p.log_of("T-1")

    def stopped(self):
        return [e["reason"] for e in self.log() if e["event"] == "stopped"]


class FromLockToMerge(Case):
    def test_a_tier_1_change_merges_itself_with_auto_merge_on(self):
        p = self.start(builder="pass2", auto_merge=True)
        result = p.drive()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events(self.log()),
                         ["started", "tests_written", "tests_reviewed", "frozen", "try_started",
                          "try_failed", "try_started", "try_passed", "ready", "merged"])
        lock = p.lock()
        self.assertEqual(lock["manifest"]["tests"], ["tests.test_t1::test_c1_shout",
                                                     "tests.test_t1::test_c2_greet_kept"])
        passed = tries(self.log())[-1]
        record = p.store.passed(passed["commit"])
        self.assertEqual((record["tier"], record["score"]), (1, 100))
        self.assertTrue(p.main_has(passed["commit"]))
        self.assertIn("merge(T-1)", p.main_log())
        # The ticket you wrote by hand on main is now the committed one, and main is clean.
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=p.project,
                                        capture_output=True, text=True, check=True).stdout, "")

    def test_a_tier_3_change_waits_for_your_approval_and_merges_after_it(self):
        p = self.start(builder="pass1", auto_merge=True, tiers={"3": ["app.py"], "4": []})
        self.assertEqual(p.drive().returncode, 0)
        self.assertEqual(events(self.log())[-1], "waiting_for_merge")
        commit = tries(self.log())[-1]["commit"]
        self.assertEqual(p.store.passed(commit)["tier"], 3)
        self.assertFalse(p.main_has(commit))
        listed = p.run("setup.merge", "list")
        self.assertIn("tier 3", listed.stdout)
        self.assertIn("needs your approval", listed.stdout)
        refused = p.run("setup.merge", "merge", commit)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("approve it first", refused.stderr)
        approved = p.run("setup.merge", "approve", commit, "--key", str(p.owner))
        self.assertEqual(approved.returncode, 0, approved.stderr)
        merged = p.run("setup.merge", "merge", commit)
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertTrue(p.main_has(commit))

    def test_the_machine_key_cannot_approve(self):
        p = self.start(builder="pass1", auto_merge=True, tiers={"3": ["app.py"], "4": []})
        p.drive()
        commit = tries(self.log())[-1]["commit"]
        from gate import sign
        refused = p.run("setup.merge", "approve", commit, "--key", str(sign.machine_key()))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("machine key", refused.stderr)
        self.assertFalse(p.main_has(commit))

    def test_a_change_under_github_is_tier_4_and_waits_for_you(self):
        p = self.start(builder="github", auto_merge=True)
        self.assertEqual(p.drive().returncode, 0)
        self.assertEqual(events(self.log())[-1], "waiting_for_merge")
        commit = tries(self.log())[-1]["commit"]
        self.assertEqual(p.store.passed(commit)["tier"], 4)
        self.assertIn("approve it first", p.run("setup.merge", "merge", commit).stderr)
        self.assertFalse(p.main_has(commit))


class BestTry(Case):
    def test_a_try_under_70_goes_back_and_the_next_try_starts_from_the_best_try(self):
        p = self.start(advisor=())
        inputs = p.root / "inputs.jsonl"
        p.commit_settings(builder=f"different inputs_to={inputs}", advisor=())
        self.assertEqual(p.drive().returncode, 3)
        done = tries(self.log())
        starts = [e["start"] for e in self.log() if e["event"] == "try_started"]
        self.assertEqual([e["event"] for e in done], ["try_failed"] * 3)
        self.assertLess(done[0]["score"], 70)
        self.assertLess(done[1]["score"], done[0]["score"])
        # Try 2 and try 3 both start from try 1, the best try so far.
        self.assertEqual(starts[1:], [done[0]["commit"], done[0]["commit"]])
        # Each try after the first gets the reasons the try before it failed.
        sent = [json.loads(line) for line in inputs.read_text().splitlines()]
        self.assertEqual([s["attempt"] for s in sent], [1, 2, 3])
        self.assertEqual(sent[0]["failed"], [])
        self.assertEqual(sent[1]["failed"], done[0]["failed"])
        self.assertTrue(sent[1]["findings"])
        self.assertEqual(self.log()[-1]["reason"], "the ticket used 3 tries")

    def test_a_checklist_pass_on_a_missing_line_keeps_the_score_under_70(self):
        p = self.start(builder="pass2", reviewer="ok badline", advisor=())
        self.assertEqual(p.drive().returncode, 3)
        scored = [e["score"] for e in tries(self.log()) if e.get("items")]
        self.assertTrue(scored)
        self.assertTrue(all(s < 70 for s in scored), scored)
        self.assertNotIn("try_passed", events(self.log()))


class StopAndAdvisor(Case):
    def test_the_stop_policy_asks_you_and_your_answer_in_the_store_unblocks_the_ticket(self):
        p = self.start(builder="same", auto_merge=True,
                       ai={"builder": f"{ROLE} same", "reviewer": f"{ROLE} ok",
                           "advisor": ["person"], "stronger_builder": f"{ROLE} pass1"})
        self.assertEqual(p.drive().returncode, 3)
        self.assertEqual(len(tries(self.log())), 2)
        self.assertIn("failed the same way", self.stopped()[0])
        questions = p.store.open_questions()
        self.assertEqual(list(questions), [1])
        self.assertEqual(questions[1]["options"], ["retry", "stronger", "split", "park"])
        # With no answer, the driver still waits.
        self.assertEqual(p.drive().returncode, 3)
        self.assertEqual(events(self.log())[-1], "still_waiting")
        inbox = p.run("setup.inbox", "--project", ".")
        self.assertIn("question 1: tollgate: ticket T-1 waits for a decision", inbox.stdout)
        answered = p.run("setup.inbox", "--project", ".", "answer", "1", "stronger",
                         "use", "the", "stronger", "builder")
        self.assertEqual(answered.returncode, 0, answered.stderr)
        result = p.drive()
        self.assertEqual(result.returncode, 0, result.stderr)
        decided = [e for e in self.log() if e["event"] == "advisor_decided"]
        self.assertEqual([(d["by"], d["decision"], d["hint"]) for d in decided],
                         [("person", "stronger", "use the stronger builder")])
        self.assertEqual(events(self.log())[-1], "merged")
        self.assertEqual(p.store.open_questions(), {})
        self.assertIsNotNone(p.store.question(1)["answer"])

    def test_an_ai_advisor_decides_at_most_twice_then_the_ticket_is_parked(self):
        p = self.start(builder="same", advisor=(f"{ROLE} ok decision=retry",))
        self.assertEqual(p.drive().returncode, 3)
        self.assertEqual(events(self.log()).count("advisor_decided"), 2)
        self.assertEqual(events(self.log())[-1], "parked")

    def test_the_ticket_cost_parks_with_no_question(self):
        p = self.start(builder="same cost=2", reviewer="ok cost=2", stop={"ticket_usd": 5})
        self.assertEqual(p.drive().returncode, 3)
        self.assertIn("the ticket cost", self.log()[-1]["reason"])
        self.assertEqual(p.store.open_questions(), {})


class Restarts(Case):
    def test_a_killed_driver_started_again_repeats_no_finished_step(self):
        p = self.start()
        marker = p.root / "died"
        p.commit_settings(builder=f"pass2 die_once={marker}")
        first = p.drive()
        self.assertEqual(first.returncode, -9, first.stderr)
        self.assertEqual(events(self.log()).count("frozen"), 1)
        self.assertEqual(tries(self.log()), [])
        second = p.drive()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(events(self.log()).count("tests_written"), 1)
        self.assertEqual(events(self.log()).count("frozen"), 1)
        self.assertEqual(p.lock()["number"], 1)
        self.assertEqual(events(self.log())[-1], "waiting_for_merge")

    def test_a_second_driver_for_the_same_ticket_refuses_to_start(self):
        p = self.start()
        holder = subprocess.Popen(["sleep", "60"])
        self.addCleanup(holder.wait)
        self.addCleanup(holder.kill)
        state.path(str(p.project), "run", "T-1.lock").write_text(str(holder.pid))
        result = p.drive()
        self.assertEqual(result.returncode, 4)
        self.assertIn("another driver holds", result.stderr)
        self.assertEqual(self.log(), [])


if __name__ == "__main__":
    unittest.main()
