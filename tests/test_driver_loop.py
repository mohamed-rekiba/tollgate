"""The driver loop, with fake roles and the fake store in tests/driver_fakes.py.

Each case builds ticket T-1 of a sample project: shout returns the greeting in
capitals. The fake builder's mode decides how each try goes.
"""

import json
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
        self.assertEqual(s.events()[-6:], ["try_failed", "try_started", "builder_said",
                                           "try_passed", "ready", "waiting_for_merge"])
        said = [e for e in s.log() if e["event"] == "builder_said"][-1]
        self.assertEqual(said["decisions"], ["shout reuses greet"])
        branch, ticket, commit = store.ready_marks[0]
        self.assertEqual((branch, ticket), ("tg/T-1", "T-1"))
        self.assertEqual(store.passed(commit)["score"], 100)
        self.assertEqual(store.merged, [])

    def test_an_existing_test_keeps_a_behavior_under_its_own_name(self):
        from tests.driver_fakes import sh
        from tests.fakes import TICKET
        s = self.sample(builder="pass2 tw_map=1")
        Path(s.project, "tests/test_greet.py").write_text(
            "import unittest\n\nimport app\n\n\nclass G(unittest.TestCase):\n"
            "    def test_greet(self):\n        self.assertEqual(app.greet('ann'), 'hello ann')\n")
        Path(s.project, ".tollgate/tickets/T-1/ticket.md").write_text(TICKET.replace(
            "tests: tests/test_t1.py", "tests: tests/test_t1.py, tests/test_greet.py"))
        sh(s.project, "git", "add", "-A")
        sh(s.project, "git", "commit", "-q", "-m", "an existing test")
        d, _ = driver(s)
        self.assertEqual(d.run(), 0)
        lock = d.lock()["manifest"]
        self.assertEqual(lock["keeps_behavior"], ["tests.test_greet::test_greet"])
        self.assertEqual(lock["items"]["tests.test_greet::test_greet"], "C2")
        passed = [e for e in s.log() if e["event"] == "try_passed"][-1]
        self.assertEqual((passed["score"], passed["items"]["C2"]), (100, True))
        self.assertEqual(sh(d.copy, "git", "diff", "main", "HEAD", "--", "tests/test_greet.py"),
                         "")

    def test_a_check_that_fails_on_the_new_tests_sends_them_back(self):
        py = sys.executable
        bad = f"{py} -c \"print('tests/test_t1.py:1: a long dash'); raise SystemExit(1)\""
        s = self.sample(checks={"tests": {"run": f"{py} run_tests.py", "report": "report.xml"},
                                "writing": {"run": bad}})
        d, _ = driver(s)
        d.run()
        rejected = [e for e in s.log() if e["event"] == "tests_rejected"]
        self.assertTrue(rejected)
        self.assertIn("tests/test_t1.py", rejected[0]["findings"][0]["text"])

    def test_a_check_failure_the_tests_did_not_cause_waits_for_the_builder(self):
        # A project with no README fails the writing check before any test is written.
        # The test writer may not write a README, so the tests go on, and the gate
        # holds the builder's try to that check.
        py = sys.executable
        bad = f"{py} -c \"print('README.md: missing.'); raise SystemExit(1)\""
        s = self.sample(checks={"tests": {"run": f"{py} run_tests.py", "report": "report.xml"},
                                "writing": {"run": bad}})
        d, _ = driver(s)
        d.run()
        events = s.events()
        self.assertNotIn("tests_rejected", events)
        self.assertIn("tests_reviewed", events)
        failed = [e for e in s.log() if e["event"] == "try_failed"]
        self.assertTrue(failed, "the gate still runs the writing check on the try")

    def test_a_tier_2_change_gets_the_review_lens(self):
        s = self.sample(reviewer="ok block=review", tier1={"max_files": 0, "max_lines": 0})
        d, store = driver(s)
        d.run()
        failed = [e for e in s.log() if e["event"] == "try_failed"]
        self.assertTrue(any("review problem" in f.get("text", "")
                            for e in failed for f in e.get("findings", [])))
        self.assertEqual(store.ready_marks, [])

    def test_the_driver_draws_a_diagram_from_the_builder_s_spec(self):
        s = self.sample(builder="good diagram=ok")
        d, store = driver(s)
        d.run()
        from tests.driver_fakes import sh
        head = store.ready_marks[-1]["commit"] if store.ready_marks else "HEAD"
        svg = sh(d.copy, "git", "show", f"{head}:docs/diagrams/shout.svg")
        self.assertIn("<svg", svg)
        self.assertNotIn("drawn by hand", svg)
        self.assertIn("<svg", sh(d.copy, "git", "show", f"{head}:docs/diagrams/shout-dark.svg"))
        drawn = [e for e in s.log() if e["event"] == "diagrams_drawn"]
        self.assertEqual(drawn[0]["folders"], ["docs/diagrams"])

    def test_the_builder_gets_the_diagram_guide_only_when_the_ticket_names_a_diagram(self):
        from driver.driver import diagram_guide
        guide = diagram_guide("- [ ] I1 (must): the README has a diagram of the flow")
        self.assertIn("# Draw a diagram", guide)
        self.assertIn("The format", guide)
        self.assertIn("Tollgate draws the SVG files", guide)
        self.assertEqual(diagram_guide("- [ ] I1 (must): shout returns capitals"), "")

    def test_the_diagram_guide_holds_every_format(self):
        from driver.driver import diagram_guide
        guide = diagram_guide("- [ ] I1 (must): a sequence diagram of the login")
        for kind in ("a flow", "a sequence diagram", "a state machine", "a C4 diagram",
                     "a use case diagram", "a class or ER diagram", "a scene"):
            self.assertIn(f"## The format of {kind}", guide)

    def test_the_driver_draws_every_kind_of_spec_the_builder_wrote(self):
        import json
        import subprocess
        import tempfile

        from driver.driver import draw_diagrams
        specs = {
            "login": {"type": "sequence", "title": "Log in", "desc": "You log in.",
                      "participants": [{"id": "you", "text": "You", "kind": "you"},
                                       {"id": "site", "text": "The site", "kind": "server"}],
                      "messages": [{"from": "you", "to": "site", "text": "log in"},
                                   {"from": "site", "to": "you", "text": "welcome",
                                    "reply": True}]},
            "order": {"type": "state", "title": "An order", "desc": "An order is paid.",
                      "states": [{"id": "start", "initial": True, "col": 0, "row": 0},
                                 {"id": "paid", "text": "Paid", "col": 1, "row": 0,
                                  "kind": "server"},
                                 {"id": "end", "final": True, "col": 2, "row": 0}],
                      "transitions": [{"from": "start", "to": "paid", "event": "pay"},
                                      {"from": "paid", "to": "end", "event": "ship"}]},
            "shop": {"type": "c4", "level": "context", "title": "A shop", "desc": "You shop.",
                     "elements": [{"id": "you", "type": "person", "name": "You",
                                   "col": 0, "row": 0},
                                  {"id": "shop", "type": "system", "name": "The shop",
                                   "col": 1, "row": 0}],
                     "relations": [{"from": "you", "to": "shop", "label": "Buys from"}]},
            "borrow": {"type": "usecase", "title": "A library", "desc": "You borrow a book.",
                       "system": "The library",
                       "actors": [{"id": "you", "name": "You", "col": 0, "row": 0}],
                       "cases": [{"id": "borrow", "name": "Borrow a book", "col": 1, "row": 0}],
                       "links": [{"from": "you", "to": "borrow"}]},
            "shapes": {"type": "class", "title": "Shapes", "desc": "A circle is a shape.",
                       "classes": [{"id": "s", "name": "Shape", "col": 0, "row": 0, "kind": "ai"},
                                   {"id": "c", "name": "Circle", "col": 0, "row": 1, "kind": "ai"}],
                       "relations": [{"from": "c", "to": "s", "type": "inherits"}]},
            "loans": {"type": "er", "title": "Loans", "desc": "A member has loans.",
                      "tables": [{"id": "m", "name": "members", "col": 0, "row": 0,
                                  "kind": "you", "columns": [{"name": "id", "key": "pk"}]},
                                 {"id": "l", "name": "loans", "col": 1, "row": 0,
                                  "kind": "server", "columns": [{"name": "member", "key": "fk"}]}],
                      "relations": [{"from": "m", "to": "l", "ends": ["one", "many"]}]},
        }
        for name, spec in specs.items():
            with self.subTest(kind=spec["type"]), tempfile.TemporaryDirectory() as copy:
                subprocess.run(["git", "init", "-q", copy], check=True)
                src = Path(copy, "docs", "diagrams", "src")
                src.mkdir(parents=True)
                (src / f"{name}.json").write_text(json.dumps(spec))
                folders, problem = draw_diagrams(copy)
                self.assertEqual((folders, problem), (["docs/diagrams"], ""))
                self.assertIn("<svg", Path(copy, "docs", "diagrams", f"{name}-dark.svg").read_text())

    def test_a_spec_of_the_wrong_shape_is_a_problem_not_a_crash(self):
        import json
        import subprocess
        import tempfile

        from driver.driver import draw_diagrams
        bad = [{"type": "state", "title": "t", "desc": "d", "states": ["x"]},
               {"type": "sequence", "title": "t", "desc": "d", "participants": ["x"],
                "messages": []},
               {"title": "t", "desc": "d", "nodes": ["x"]}]
        for spec in bad:
            with self.subTest(kind=spec.get("type", "flow")), \
                    tempfile.TemporaryDirectory() as copy:
                subprocess.run(["git", "init", "-q", copy], check=True)
                src = Path(copy, "docs", "diagrams", "src")
                src.mkdir(parents=True)
                (src / "bad.json").write_text(json.dumps(spec))
                folders, problem = draw_diagrams(copy)
                self.assertEqual(folders, ["docs/diagrams"])
                self.assertIn("cannot be drawn", problem)

    def test_a_spec_that_cannot_be_drawn_fails_the_try(self):
        s = self.sample(builder="good diagram=bad")
        d, _ = driver(s)
        d.run()
        failed = [e for e in s.log() if e["event"] == "try_failed"]
        self.assertTrue(failed)
        self.assertIn("cannot be drawn", failed[0]["findings"][0]["text"])

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


class ChecklistTest(LoopCase):
    def test_the_builder_s_own_test_does_not_vouch_for_an_item(self):
        path = s_path()
        self.addCleanup(Path(path).unlink, missing_ok=True)
        s = self.sample(builder="pass1 owntest=1", reviewer=f"ok review_to={path}")
        d, _ = driver(s)
        self.assertEqual(d.run(), 0)
        seen = [json.loads(line) for line in Path(path).read_text().splitlines()]
        self.assertNotIn("C3", seen[-1]["tested"])
        self.assertEqual(sorted(seen[-1]["tested"]), ["C1", "C2"])
        passed = [e for e in s.log() if e["event"] == "try_passed"][-1]
        self.assertEqual((passed["score"], passed["items"]["C3"]), (100, True))

    def test_a_low_score_tells_the_builder_which_items_failed_and_why(self):
        inputs = s_path()
        self.addCleanup(Path(inputs).unlink, missing_ok=True)
        s = self.sample(builder=f"pass1 inputs_to={inputs}", reviewer="ok c3fail",
                        pass_score=70)
        d, _ = driver(s)
        d.run()
        failed = next(e for e in s.log() if e["event"] == "try_failed")
        text = " ".join(f["text"] for f in failed["findings"])
        self.assertIn("score 67 is under 70", text)
        self.assertIn("C3", text)
        self.assertIn("shout has no docstring", text)
        second = [json.loads(line) for line in Path(inputs).read_text().splitlines()][1]
        self.assertIn("shout has no docstring", " ".join(f["text"] for f in second["findings"]))


def s_path():
    """A file outside the copy for a fake role to write to, new for each call."""
    import tempfile
    handle, path = tempfile.mkstemp(suffix=".jsonl")
    import os
    os.close(handle)
    os.unlink(path)
    return path


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

    def task(self, advisor="ok", **settings_args):
        from driver.task import Task
        from tests.driver_fakes import gate_api, review_api
        s = Sample(ticket=False, advisor=(f"{sys.executable} {FAKE_ROLE} {advisor}",),
                   **settings_args)
        self.addCleanup(s.close)
        store = FakeStore(s.project)
        task = Task(str(s.project), "demo", "Add shout and whisper.", store,
                    driver_args={"gate_api": gate_api(), "review_api": review_api()})
        return s, task

    def test_the_analysis_comes_first_and_travels_with_the_plan(self):
        s, task = self.task()
        self.assertEqual(task.run(), 0)
        events = s.events("task-demo")
        self.assertLess(events.index("analysis_written"), events.index("plan_written"))
        from tests.driver_fakes import sh
        text = sh(s.project, "git", "show", "tg-plan/demo:.tollgate/analysis/demo.md")
        self.assertIn("commit: " + sh(s.project, "git", "rev-parse", "main"), text)
        self.assertIn("- confirmed: greet builds the greeting [app.py::greet]", text)

    def test_a_citation_that_does_not_exist_becomes_an_assumption(self):
        s, task = self.task(reviewer="ok badcite")
        self.assertEqual(task.run(), 0)
        written = next(e for e in s.log("task-demo") if e["event"] == "analysis_written")
        self.assertEqual(written["not_found"], ["app.py::nope"])

    def test_a_plan_with_no_checkpoint_and_no_assumptions_needs_no_advisor(self):
        s, task = self.task(checkpoints=[])
        self.assertEqual(task.run(), 0)
        events = s.events("task-demo")
        self.assertIn("plan_approved", events)
        self.assertNotIn("advisor_decided", events[:events.index("plan_locked")])

    def test_a_plan_with_an_assumption_always_goes_to_the_advisor(self):
        s, task = self.task(builder="pass2 ask=1", checkpoints=[], advisor="ok plan_decision=send_back")
        self.assertEqual(task.run(), 3)
        log = s.log("task-demo")
        self.assertIn("advisor_decided", [e["event"] for e in log])
        self.assertIn("plan_sent_back", [e["event"] for e in log])

    def test_a_ticket_checkpoint_can_stop_the_task(self):
        s, task = self.task(checkpoints=["ticket"], advisor="ok checkpoint=stop")
        self.assertEqual(task.run(), 3)
        done = [e["ticket"] for e in s.log("task-demo") if e["event"] == "ticket_done"]
        self.assertEqual(done, ["demo-1"])
        self.assertIn("checkpoint_stopped", s.events("task-demo"))

    def test_the_whole_task_is_reviewed_after_the_last_ticket(self):
        s, task = self.task(checkpoints=[])
        self.assertEqual(task.run(), 0)
        log = s.log("task-demo")
        reviewed = [e for e in log if e["event"] == "task_reviewed"]
        self.assertEqual(len(reviewed), 1)
        self.assertTrue(reviewed[0]["passed"])
        events = [e["event"] for e in log]
        self.assertLess(max(i for i, e in enumerate(events) if e == "ticket_done"),
                        events.index("task_reviewed"))
        text = Path(state.path(str(s.project), "reports", "demo.md")).read_text()
        self.assertIn("- Analysis: written. Every citation was found.", text)
        self.assertIn("## The review of the whole task\n\nPassed. Tier 2.", text)

    def test_a_blocking_finding_after_the_fix_round_parks_the_task(self):
        s, task = self.task(checkpoints=[], reviewer="ok block=review", advisor="ok")
        # The sample tickets are tier 1, so only the review of the whole task blocks.
        self.assertEqual(task.run(), 3)
        reviewed = [e for e in s.log("task-demo") if e["event"] == "task_reviewed"]
        self.assertEqual([e["passed"] for e in reviewed], [False, False])
        self.assertIn("fix_round", s.events("task-demo"))
        self.assertNotIn("checkpoint_passed", s.events("task-demo"))


    def test_an_analysis_that_cannot_be_read_parks_the_task(self):
        s, task = self.task(reviewer="ok badanalysis")
        self.assertEqual(task.run(), 3)
        events = s.events("task-demo")
        self.assertEqual(events.count("analysis_invalid"), 3)
        self.assertIn("task_waiting", events)
        self.assertNotIn("plan_written", events)

    def test_a_stop_holds_when_the_task_starts_again(self):
        s, task = self.task(checkpoints=["ticket"], advisor="ok checkpoint=stop")
        self.assertEqual(task.run(), 3)
        self.assertEqual(task.run(), 3)
        log = s.log("task-demo")
        self.assertEqual([e["event"] for e in log].count("checkpoint_stopped"), 1)
        self.assertEqual(len([e for e in log if e["event"] == "advisor_decided"]), 1)

    def test_a_merged_ticket_stays_in_the_review_of_the_whole_task(self):
        s, task = self.task(checkpoints=[], auto_merge=True)
        self.assertEqual(task.run(), 0)
        reviewed = next(e for e in s.log("task-demo") if e["event"] == "task_reviewed")
        self.assertIn("demo-2", reviewed.get("tickets", []))
        self.assertIn("demo-1", reviewed.get("tickets", []))



class FixRoundTest(LoopCase):
    """The review of the whole task finds a problem: one fix round, then merges in order."""

    def task(self, advisor="ok", **settings_args):
        from driver.task import Task
        from tests.driver_fakes import gate_api, review_api
        s = Sample(ticket=False, advisor=(f"{sys.executable} {FAKE_ROLE} {advisor}",),
                   **settings_args)
        self.addCleanup(s.close)
        store = FakeStore(s.project)
        task = Task(str(s.project), "demo", "Add shout and whisper.", store,
                    driver_args={"gate_api": gate_api(), "review_api": review_api()})
        return s, store, task

    def ready(self, s, tid):
        return [e for e in s.log(tid) if e["event"] == "ready"][-1]["commit"]

    def test_a_failed_task_review_runs_one_fix_round_then_merges_in_plan_order(self):
        s, store, task = self.task(reviewer="ok taskmajor=1", auto_merge=True)
        self.assertEqual(task.run(), 0)
        events = s.events("task-demo")
        self.assertEqual(events.count("fix_round"), 1)
        rounds = [e.get("round") for e in s.log("task-demo") if e["event"] == "task_reviewed"]
        self.assertEqual(rounds, [0, 1])
        self.assertEqual([m[1] for m in store.ready_marks], ["demo-1", "demo-2", "demo-3"])
        self.assertEqual(store.merged, [self.ready(s, t) for t in ("demo-1", "demo-2", "demo-3")])
        plan = json.loads(state.path(str(s.project), "plans", "demo.json").read_text())
        self.assertIn(".tollgate/tickets/demo-3/ticket.md", plan["files"])

    def test_each_ticket_starts_from_the_ready_change_before_it(self):
        s, store, task = self.task(reviewer="ok taskmajor=1")
        self.assertEqual(task.run(), 0)
        self.assertEqual(store.starts["demo-1"], None)
        self.assertEqual(store.starts["demo-2"], self.ready(s, "demo-1"))
        self.assertEqual(store.starts["demo-3"], self.ready(s, "demo-2"))
        lock = json.loads(state.path(str(s.project), "locks", "demo-3.json").read_text())
        self.assertEqual(lock["base_commit"], self.ready(s, "demo-2"))

    def test_a_second_failure_parks_and_nothing_merges_whatever_the_advisor_says(self):
        s, store, task = self.task(reviewer="ok taskmajor=2", advisor="ok checkpoint=continue",
                                   auto_merge=True)
        self.assertEqual(task.run(), 3)
        log = s.log("task-demo")
        events = [e["event"] for e in log]
        self.assertEqual(events.count("fix_round"), 1)
        self.assertFalse([e for e in log if e.get("checkpoint") == "task"
                          or e.get("name") == "task"])
        waiting = [e for e in log if e["event"] == "task_waiting"][-1]
        self.assertIn("after the fix round", waiting["reason"])
        self.assertEqual(store.merged, [])
        for tid in ("demo-1", "demo-2", "demo-3"):
            self.assertEqual(s.events(tid)[-1], "waiting_for_merge")

    def test_the_tickets_stop_at_the_first_that_does_not_end_ready(self):
        s, _, task = self.task(builder="same", advisor="ok decision=park")
        self.assertEqual(task.run(), 3)
        self.assertIn("parked", s.events("demo-1"))
        self.assertEqual(s.log("demo-2"), [])

    def test_no_ticket_merges_before_the_task_review_passes(self):
        s, store, task = self.task(reviewer="ok taskmajor=1", auto_merge=True)
        merged_at = []
        real = store.merge

        def merge(commit):
            merged_at.append([e["event"] for e in s.log("task-demo")])
            return real(commit)
        store.merge = merge
        self.assertEqual(task.run(), 0)
        for seen in merged_at:
            self.assertIn("checkpoint_passed", seen)
            self.assertEqual([e for e in seen if e == "task_reviewed"], ["task_reviewed"] * 2)


if __name__ == "__main__":
    unittest.main()
