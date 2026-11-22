"""The driver loop, with fake roles and the fake store in tests/driver_fakes.py.

Each case builds ticket T-1 of a sample project: shout returns the greeting in
capitals. The fake builder's mode decides how each try goes.
"""

import sys
import unittest
from pathlib import Path

from driver import history
from gate import state
from gate.store import StoreError
from tests.driver_fakes import FAKE_ROLE, FakeStore, Refusing, Sample, driver, gate_api


class LoopCase(unittest.TestCase):
    def sample(self, **settings_args):
        s = Sample(**settings_args)
        self.addCleanup(s.close)
        return s

    def tries(self, s):
        return [e for e in s.log() if e["event"] in ("try_failed", "try_passed")]


class BuildTest(LoopCase):
    def test_a_failed_try_then_a_pass_makes_a_ready_change(self):
        s = self.sample()
        d, store = driver(s)
        self.assertEqual(d.run(), 0)
        self.assertEqual(s.events()[-5:], ["try_failed", "try_started", "try_passed", "ready",
                                           "waiting_for_merge"])
        branch, ticket, commit = store.ready_marks[0]
        self.assertEqual((branch, ticket), ("tg/T-1", "T-1"))
        self.assertEqual(store.passed(commit)["score"], 100)
        self.assertEqual(store.merged, [])

    def test_nothing_the_driver_writes_stays_in_the_project(self):
        s = self.sample()
        driver(s)[0].run()
        found = sorted(str(p.relative_to(s.project)) for p in (s.project / ".tollgate").rglob("*")
                       if p.is_file())
        self.assertEqual(found, [".tollgate/settings.json", ".tollgate/tickets/T-1/ticket.md"])
        self.assertTrue(state.path(str(s.project), "builders", "T-1").is_dir())
        self.assertTrue(state.path(str(s.project), "logs", "T-1.jsonl").exists())

    def test_a_second_run_repeats_no_finished_step(self):
        s = self.sample()
        d, store = driver(s)
        d.run()
        before = len(s.log())
        self.assertEqual(driver(s, store=store)[0].run(), 0)
        self.assertEqual(store.freezes, 1)
        self.assertEqual(s.events()[before:], ["started", "waiting_for_merge"])


class MergeTest(LoopCase):
    def test_tier_1_merges_with_auto_merge(self):
        s = self.sample(auto_merge=True)
        d, store = driver(s)
        self.assertEqual(d.run(), 0)
        self.assertEqual(s.events()[-1], "merged")
        self.assertEqual(store.merged, [store.ready_marks[0][2]])

    def test_tier_3_never_merges(self):
        s = self.sample(auto_merge=True, tiers={"3": ["app.py"], "4": []})
        d, store = driver(s)
        self.assertEqual(d.run(), 0)
        self.assertEqual(s.events()[-1], "waiting_for_merge")
        self.assertEqual(self.tries(s)[-1]["tier"], 3)
        self.assertEqual(store.merged, [])

    def test_a_merge_the_store_refuses_leaves_a_ready_change(self):
        s = self.sample(auto_merge=True)
        store = FakeStore(s.project)
        store.merge = lambda commit: (_ for _ in ()).throw(StoreError("the main worktree has changes"))
        d, _ = driver(s, store=store)
        self.assertEqual(d.run(), 0)
        self.assertEqual(s.events()[-1], "waiting_for_merge")
        self.assertIn("the main worktree has changes", s.log()[-1]["reason"])

    def test_no_auto_merge_waits_for_you(self):
        s = self.sample(auto_merge=False)
        d, store = driver(s)
        d.run()
        self.assertEqual((s.events()[-1], store.merged), ("waiting_for_merge", []))


class HillClimbTest(LoopCase):
    def test_each_try_starts_from_the_best_try_so_far(self):
        # Try 1 scores 67. Try 2 breaks greet and scores less. Try 3 starts from try 1.
        s = self.sample(builder="different", advisor=())
        driver(s)[0].run()
        starts = [e["start"] for e in s.log() if e["event"] == "try_started"]
        tries = self.tries(s)
        self.assertGreater(tries[0]["score"], tries[1]["score"])
        self.assertEqual(starts[1], tries[0]["commit"])
        self.assertEqual(starts[2], tries[0]["commit"])

    def test_a_try_that_scores_higher_becomes_the_best(self):
        t = history.replay([{"event": "frozen", "commit": "c0"},
                            {"event": "try_failed", "attempt": 1, "commit": "c1", "score": 33},
                            {"event": "try_failed", "attempt": 2, "commit": "c2", "score": 67},
                            {"event": "try_failed", "attempt": 3, "commit": "c3", "score": 67}])
        self.assertEqual((t.best_commit, t.best_score), ("c2", 67))
        st_ = history.Ticket(best_commit="c2", best_score=67)
        from driver.driver import Driver
        Driver._keep_if_best(st_, 67, "c3")
        self.assertEqual(st_.best_commit, "c2")
        Driver._keep_if_best(st_, 68, "c4")
        self.assertEqual(st_.best_commit, "c4")


class StopTest(LoopCase):
    def test_the_same_failure_twice_asks_you_and_your_answer_is_read(self):
        s = self.sample(builder="same")
        d, store = driver(s)
        self.assertEqual(d.run(), 3)
        self.assertEqual(len(self.tries(s)), 2)
        stopped = [e["reason"] for e in s.log() if e["event"] == "stopped"]
        self.assertIn("failed the same way", stopped[0])
        n = s.log()[-1]["question"]
        self.assertEqual(list(store.open_questions()), [n])
        self.assertEqual(driver(s, store=store)[0].run(), 3)
        self.assertEqual(s.events()[-1], "still_waiting")
        store.answer(n, "tollgate decide retry look at shout")
        driver(s, store=store)[0].run()
        decided = next(e for e in s.log() if e["event"] == "advisor_decided")
        self.assertEqual((decided["decision"], decided["hint"]), ("retry", "look at shout"))
        self.assertEqual(len(self.tries(s)), 3)
        self.assertIsNotNone(store.question(n)["answer"])
        # Try 3 failed the same way as try 2, so a new question waits.
        self.assertEqual(list(store.open_questions()), [n + 1])

    def test_split_is_unfinished_and_parks_the_ticket_plainly(self):
        from driver import report
        s = self.sample(builder="same")
        d, store = driver(s)
        self.assertEqual(d.run(), 3)
        n = s.log()[-1]["question"]
        store.answer(n, "split")
        self.assertEqual(driver(s, store=store)[0].run(), 3)
        self.assertEqual(s.events()[-1], "parked")
        self.assertIn("split: UNFINISHED, parked", s.log()[-1]["reason"])
        self.assertIn("split: UNFINISHED, parked", report.status(str(s.project)))

    def test_three_tries_stop(self):
        s = self.sample(builder="different", advisor=())
        self.assertEqual(driver(s)[0].run(), 3)
        self.assertEqual(len(self.tries(s)), 3)
        self.assertEqual(s.log()[-1]["reason"], "the ticket used 3 tries")

    def test_a_slow_try_stops(self):
        s = self.sample(builder="slow", advisor=(), stop={"attempt_minutes": 0.05})
        self.assertEqual(driver(s)[0].run(), 3)
        self.assertTrue(self.tries(s)[0]["timed_out"])
        self.assertIn("ran past", s.log()[-1]["reason"])

    def test_the_ticket_cost_parks_with_no_question(self):
        s = self.sample(builder="pass2 cost=1", reviewer="ok cost=1", stop={"ticket_usd": 3})
        d, store = driver(s)
        self.assertEqual(d.run(), 3)
        self.assertEqual(s.events()[-1], "parked")
        self.assertIn("the ticket cost", s.log()[-1]["reason"])
        self.assertEqual(store.open_questions(), {})

    def test_a_finding_the_builder_cannot_fix_goes_to_the_advisor(self):
        py = sys.executable
        s = self.sample(builder="pass1", advisor=(f"{py} {FAKE_ROLE} ok decision=park",))
        d, _ = driver(s, gate=Refusing(gate_api()))
        self.assertEqual(d.run(), 3)
        self.assertEqual(len(self.tries(s)), 1)
        stopped = [e["reason"] for e in s.log() if e["event"] == "stopped"]
        self.assertIn("cannot fix: the lock does not verify", stopped[0])
        self.assertEqual(s.log()[-1]["reason"], "the advisor chose park")

    def test_an_ai_retry_gives_one_more_try(self):
        py = sys.executable
        s = self.sample(builder="same", advisor=(f"{py} {FAKE_ROLE} ok decision=retry",
                                                 "person"))
        d, _ = driver(s)
        self.assertEqual(d.run(), 3)
        decided = [e for e in s.log() if e["event"] == "advisor_decided"]
        self.assertEqual([e["decision"] for e in decided], ["retry", "retry"])
        self.assertEqual(len(self.tries(s)), 4)
        self.assertEqual(s.events()[-1], "waiting_for_advisor")


class TaskTest(LoopCase):
    def test_a_task_plans_locks_the_plan_and_builds_each_ticket(self):
        from driver.task import Task
        from tests.driver_fakes import gate_api, review_api
        py = sys.executable
        s = Sample(ticket=False, advisor=(f"{py} {FAKE_ROLE} ok",))
        self.addCleanup(s.close)
        store = FakeStore(s.project)
        task = Task(str(s.project), "demo", "Add shout and whisper.", store,
                    driver_args={"gate_api": gate_api(), "review_api": review_api()})
        self.assertEqual(task.run(), 0)
        self.assertTrue(state.path(str(s.project), "plans", "demo.json").exists())
        self.assertEqual([m[1] for m in store.ready_marks], ["demo-1", "demo-2"])
        self.assertTrue(state.path(str(s.project), "reports", "demo.md").exists())
        self.assertFalse(Path(s.project, ".tollgate", "plans").exists())
        self.assertIn("demo-2", Path(state.path(str(s.project), "reports", "demo.md")).read_text())


if __name__ == "__main__":
    unittest.main()
