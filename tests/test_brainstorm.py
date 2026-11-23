"""The brainstorm: a rough idea becomes a brief that /tollgate:task can take.

The fake role in tests/fake_role.py stands in for each role: the builder asks the
questions, states the idea, and writes the brief; the advisor answers; the analyst
and four lenses read the idea.
"""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from driver import brainstorm as bs
from driver import session
from gate import brief as bf
from gate import state
from tests.driver_fakes import FAKE_ROLE, FakeStore, Sample, sh
from tests.test_session import fake_answer

IDEA = "A louder greeting, maybe.\n"
PY = sys.executable
AI = (f"{PY} {FAKE_ROLE} ok",)


def ai(options=""):
    return (f"{PY} {FAKE_ROLE} ok {options}".strip(),)


class Case(unittest.TestCase):
    def sample(self, builder="pass2", advisor=AI, runner="background", **settings_args):
        s = Sample(ticket=False, builder=builder, advisor=advisor, runner=runner,
                   **settings_args)
        self.addCleanup(s.close)
        Path(s.project, bf.IDEAS).mkdir(parents=True)
        Path(s.project, bf.idea_path("demo")).write_text(IDEA)
        return s, FakeStore(s.project)

    def run_it(self, s, store):
        return bs.Brainstorm(str(s.project), "demo", IDEA, store).run()

    def events(self, s):
        return s.events("brainstorm-demo")

    def log(self, s):
        return s.log("brainstorm-demo")

    def brief(self, s):
        return bf.parse(Path(s.project, bf.brief_path("demo")).read_text())

    def tmp(self, s, name):
        return str(Path(s.root, name))


class BackgroundTest(Case):
    def test_an_idea_becomes_a_brief_after_questions_readiness_analysis_and_four_lenses(self):
        s, store = self.sample()
        seen = self.tmp(s, "lenses.jsonl")
        s.commit_settings(builder="pass2", advisor=ai(), runner="background",
                          reviewer=f"ok idea_review_to={seen}")
        self.assertEqual(self.run_it(s, store), 0)
        events = self.events(s)
        self.assertEqual(events, [
            "started", "asked", "answered", "asked", "answered", "stated", "confirmed",
            "analysis_written", "idea_reviewed", "idea_reviewed", "idea_reviewed",
            "idea_reviewed", "brief_written"])
        answered = [e for e in self.log(s) if e["event"] == "answered"]
        self.assertEqual([e["by"] for e in answered], ["ai", "ai"])
        self.assertEqual(answered[0]["answer"], "Ann, who greets her friends.")
        found = self.brief(s)
        self.assertEqual((found.id, found.size), ("demo", "task"))
        # The lenses agree on one thing: the brief says it once.
        self.assertEqual(found.sections["Analysis"].count("greet already builds"), 1)
        self.assertEqual(found.alternatives[0][0], "A loud flag on greet")
        # Each lens is fresh: it reads the same inputs and none of the others' findings.
        lenses = [json.loads(x) for x in Path(seen).read_text().splitlines()]
        self.assertEqual(sorted(x["lens"] for x in lenses), ["need", "risk", "shape", "user"])
        self.assertEqual(len({json.dumps(x["inputs"], sort_keys=True) for x in lenses}), 1)
        self.assertNotIn("findings", lenses[0]["inputs"])
        self.assertIn("confirmed: greet builds the greeting", lenses[0]["inputs"]["analysis"])
        # The copy goes, and a second run does nothing more.
        self.assertFalse(state.path(str(s.project), "builders", "brainstorm-demo").exists())
        self.assertEqual(self.run_it(s, store), 0)
        self.assertEqual(self.events(s), events)

    def test_the_questions_stop_at_the_cap(self):
        s, store = self.sample()
        seen = self.tmp(s, "ideas.jsonl")
        s.commit_settings(builder=f"pass2 questions=9 idea_to={seen}", advisor=ai(),
                          runner="background")
        self.assertEqual(self.run_it(s, store), 0)
        self.assertEqual(self.events(s).count("asked"), bs.MAX_QUESTIONS)
        left = [json.loads(x)["questions_left"] for x in Path(seen).read_text().splitlines()]
        self.assertEqual(left, [5, 4, 3, 2, 1, 0])
        self.assertIn("stated", self.events(s))

    def test_a_builder_that_asks_past_the_cap_parks_the_brainstorm(self):
        s, store = self.sample(builder="pass2 questions=always")
        self.assertEqual(self.run_it(s, store), 3)
        self.assertEqual(self.events(s).count("asked"), bs.MAX_QUESTIONS)
        waiting = [e for e in self.log(s) if e["event"] == "brainstorm_waiting"]
        self.assertIn("no questions are left", waiting[-1]["reason"])
        self.assertFalse(Path(s.project, bf.brief_path("demo")).exists())

    def test_a_skipped_question_becomes_an_open_question_of_the_brief(self):
        s, store = self.sample(advisor=ai("idea=skip"))
        self.assertEqual(self.run_it(s, store), 0)
        self.assertEqual(self.brief(s).open_questions,
                         ["Who uses shout, in round 1?", "Who uses shout, in round 2?"])

    def test_the_advisor_adds_what_the_statement_misses(self):
        s, store = self.sample(advisor=ai("statement=add"))
        seen = self.tmp(s, "ideas.jsonl")
        s.commit_settings(builder=f"pass2 idea_to={seen}", advisor=ai("statement=add"),
                          runner="background")
        self.assertEqual(self.run_it(s, store), 0)
        events = self.events(s)
        self.assertEqual(events[5:9], ["stated", "changed", "stated", "confirmed"])
        last = json.loads(Path(seen).read_text().splitlines()[-1])
        self.assertEqual(last["additions"], ["It must work for an empty name."])

    def test_a_statement_never_confirmed_parks_after_the_cap(self):
        s, store = self.sample(advisor=ai("statement=always"))
        self.assertEqual(self.run_it(s, store), 3)
        self.assertEqual(self.events(s).count("changed"), bs.MAX_STATEMENTS)
        waiting = [e for e in self.log(s) if e["event"] == "brainstorm_waiting"]
        self.assertIn("did not confirm", waiting[-1]["reason"])

    def test_a_project_with_no_code_skips_the_analyst(self):
        s, store = self.sample()
        sh(s.project, "git", "rm", "-q", "app.py", "run_tests.py", "tests/__init__.py")
        sh(s.project, "git", "commit", "-q", "-m", "no code")
        self.assertEqual(self.run_it(s, store), 0)
        events = self.events(s)
        self.assertIn("analysis_skipped", events)
        self.assertNotIn("analysis_written", events)

    def test_a_brief_in_a_bad_format_is_written_again_with_the_problem(self):
        s, store = self.sample(builder="pass2 brief=bad")
        self.assertEqual(self.run_it(s, store), 0)
        invalid = [e for e in self.log(s) if e["event"] == "brief_invalid"]
        self.assertEqual(len(invalid), 1)
        self.assertIn("Goals", invalid[0]["problems"][0])
        self.assertEqual(self.brief(s).goals, ['shout("ann") returns "HELLO ANN".'])

    def test_a_brief_that_never_reads_parks_and_writes_no_file(self):
        s, store = self.sample(builder="pass2 brief=never")
        self.assertEqual(self.run_it(s, store), 3)
        self.assertEqual(self.events(s).count("brief_invalid"), bs.BRIEF_TRIES)
        self.assertFalse(Path(s.project, bf.brief_path("demo")).exists())

    def test_a_person_answers_each_question_through_the_inbox(self):
        s, store = self.sample(advisor=("person",))
        decisions = iter(["answer Ann greets her friends.", "skip", "confirm"])
        for _ in range(10):
            code = self.run_it(s, store)
            if code == 0:
                break
            self.assertEqual(code, 3)
            n, q = next(iter(store.open_questions().items()))
            self.assertIn("brainstorm demo", q["title"])
            store.answer(n, f"tollgate decide {next(decisions)}")
        self.assertEqual(code, 0)
        answered = [e for e in self.log(s) if e["event"] == "answered"]
        self.assertEqual([(e["by"], e["answer"]) for e in answered],
                         [("person", "Ann greets her friends."), ("person", "")])
        self.assertEqual(self.brief(s).open_questions, ["Who uses shout, in round 2?"])

    def test_an_id_that_is_not_a_plain_name_is_refused(self):
        s, store = self.sample()
        with self.assertRaises(bf.BriefError):
            bs.Brainstorm(str(s.project), "../x", IDEA, store)

    def test_the_command_needs_the_idea(self):
        s, store = self.sample()
        Path(s.project, bf.idea_path("demo")).unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            code = bs.main(["--project", str(s.project), "--brainstorm", "demo"], store)
        self.assertEqual(code, 1)
        self.assertIn(bf.idea_path("demo"), err.getvalue())


class SessionTest(Case):
    """driver.step next --brainstorm and answer, as the brainstorm skill runs them."""

    def step(self, store, *argv, stdin=""):
        from driver import step
        out = io.StringIO()
        with redirect_stdout(out):
            code = step.main(list(argv), store=store, stdin=io.StringIO(stdin))
        return code, json.loads(out.getvalue())

    def next(self, s, store):
        return self.step(store, "next", "--project", str(s.project), "--brainstorm", "demo")

    def loop(self, s, store, decide=lambda q: "confirm", mode="pass2"):
        code, out = self.next(s, store)
        agents = []
        for _ in range(60):
            self.assertEqual(code, 0, out)
            if "question" in out:
                store.answer(out["question"]["n"], f"tollgate decide {decide(out['question'])}")
                code, out = self.next(s, store)
                continue
            if out.get("done") or "parked" in out:
                return out, agents
            agents.append(out["agent"])
            code, out = self.step(store, "answer", "--project", str(s.project), "--key",
                                  out["key"], "--nonce", out["nonce"],
                                  stdin=fake_answer(out, mode))
        self.fail(f"the brainstorm did not end: {out}")

    def test_a_person_answers_in_session_mode(self):
        s, store = self.sample(advisor=("person",), runner="session")
        out, agents = self.loop(s, store, lambda q: "answer Ann." if "answer" in q["options"]
                                else "confirm")
        self.assertTrue(out["done"], out)
        self.assertEqual(out["brief"], str(Path(s.project, bf.brief_path("demo")).resolve()))
        self.assertEqual(out["size"], "task")
        self.assertEqual(agents[:1], ["tollgate:builder"])
        self.assertIn("tollgate:analyst", agents)
        self.assertEqual(agents.count("tollgate:reviewer"), 4)
        self.assertNotIn("tollgate:advisor", agents)
        self.assertIsNone(session.read_step(str(s.project)))

    def test_an_ai_advisor_runs_as_a_step_and_each_event_is_logged_once(self):
        s, store = self.sample(runner="session")
        out, agents = self.loop(s, store, mode="pass2 brief=bad")
        self.assertTrue(out["done"], out)
        self.assertEqual(agents.count("tollgate:advisor"), 3)  # two questions, one statement
        events = self.events(s)
        self.assertEqual(events.count("started"), 1)
        self.assertEqual(events.count("asked"), 2)
        self.assertEqual(events.count("brief_invalid"), 1)
        lines = [json.dumps({k: v for k, v in e.items() if k != "at"}, sort_keys=True)
                 for e in self.log(s)]
        self.assertEqual(len(lines), len(set(lines)))

    def test_next_with_no_idea_is_an_error(self):
        s, store = self.sample(runner="session")
        Path(s.project, bf.idea_path("demo")).unlink()
        code, out = self.next(s, store)
        self.assertEqual(code, 1)
        self.assertIn(bf.idea_path("demo"), out["error"])

    def test_a_brainstorm_is_not_a_ticket_in_the_status(self):
        from driver import report
        s, store = self.sample()
        self.assertEqual(self.run_it(s, store), 0)
        self.assertEqual(report.rows(str(s.project)), [])


class TaskFromBriefTest(Case):
    def brief_text(self, size="task"):
        from tests.test_brief import BRIEF
        return BRIEF.replace("id: shout", "id: demo").replace("size: task", f"size: {size}")

    def task(self, s, store, text):
        from driver.task import Task
        from tests.driver_fakes import gate_api, review_api
        return Task(str(s.project), "demo", text, store,
                    driver_args={"gate_api": gate_api(), "review_api": review_api()})

    def test_the_open_questions_of_the_brief_become_the_plan_s_assumptions(self):
        s, store = self.sample(advisor=("person",), checkpoints=[])
        self.assertEqual(self.task(s, store, self.brief_text()).run(), 3)
        (_, q), = store.open_questions().items()
        self.assertIn("- Should shout keep accents?", q["body"])
        written = [e for e in s.log("task-demo") if e["event"] == "plan_written"]
        self.assertEqual(len(written), 1)

    def test_a_plan_that_drops_an_open_question_is_written_again(self):
        s, store = self.sample(builder="pass2 drop_questions=1", checkpoints=[])
        with self.assertRaises(Exception) as err:
            self.task(s, store, self.brief_text()).run()
        self.assertIn("Should shout keep accents?", str(err.exception))
        invalid = [e for e in s.log("task-demo") if e["event"] == "plan_invalid"]
        self.assertIn("Assumptions", invalid[0]["problems"][0])

    def test_a_brief_too_big_for_one_task_points_to_the_roadmap(self):
        from gate import plan as pl
        s, store = self.sample()
        with self.assertRaises(pl.PlanError) as err:
            self.task(s, store, self.brief_text("roadmap"))
        self.assertIn("roadmap", str(err.exception))
        self.assertIn(".tollgate/roadmaps/demo.md", str(err.exception))

    def test_a_brief_in_a_bad_format_is_refused_as_a_request(self):
        from gate import plan as pl
        s, store = self.sample()
        with self.assertRaises(pl.PlanError) as err:
            self.task(s, store, self.brief_text().replace("## Goals", "## Aims"))
        self.assertIn("Goals", str(err.exception))

    def test_the_task_command_takes_a_brief_by_its_id(self):
        from unittest import mock

        from driver import task as tk
        s, store = self.sample()
        Path(s.project, bf.BRIEFS).mkdir(parents=True)
        Path(s.project, bf.brief_path("demo")).write_text(self.brief_text())
        with mock.patch.object(tk.Task, "run", return_value=0) as run:
            self.assertEqual(tk.main(["--project", str(s.project), "--task", "demo",
                                      "--brief", "demo"], store), 0)
        run.assert_called_once()
        err = io.StringIO()
        with redirect_stderr(err):
            code = tk.main(["--project", str(s.project), "--task", "demo", "--brief", "nope"],
                           store)
        self.assertEqual(code, 1)
        self.assertIn("/tollgate:brainstorm", err.getvalue())


if __name__ == "__main__":
    unittest.main()
