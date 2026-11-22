"""Session mode: your own Claude Code session runs each role as a subagent.

The fake role in tests/fake_role.py stands in for the subagent: the test runs it
in the step's folder with the step's prompt, and hands its answer to
`driver.step answer`, as the task skill does with a subagent's answer.
"""

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from driver import roles, session
from gate import state
from tests.driver_fakes import FAKE_ROLE, FakeStore, Sample, driver, sh


def fake_answer(step: dict, mode: str = "pass2") -> str:
    """What the subagent says: the fake role run in the step's folder with its prompt."""
    done = subprocess.run([sys.executable, FAKE_ROLE, mode, "cost=0.1"], input=step["prompt"],
                          cwd=step["cwd"] if "cwd" in step else step["copy"],
                          capture_output=True, text=True, check=True)
    return json.loads(done.stdout)["result"]


class Case(unittest.TestCase):
    def sample(self, **settings_args):
        s = Sample(**{"runner": "session", **settings_args})
        self.addCleanup(s.close)
        return s

    def call(self, s, role="reviewer", inputs=None, lens="test_fit", copy=None):
        return session.Call(role=role, inputs=inputs or {"x": 1}, lens=lens, command="claude -p",
                            policy=role, copy=str(copy or s.project), project=str(s.project),
                            log="T-1", ticket="T-1", task="retries")


class CallerTest(Case):
    def test_the_background_caller_is_today_s_role_run(self):
        s = self.sample()
        settings = {"stop": {"attempt_minutes": 7}, "isolation": "sandbox",
                    "container_image": "img", "runner": "background"}
        caller = session.caller(settings)
        self.assertIsInstance(caller, session.Background)
        with mock.patch.object(roles, "run", return_value="answer") as run:
            self.assertEqual(caller(self.call(s)), "answer")
        run.assert_called_once_with("claude -p", "reviewer", {"x": 1}, str(s.project), 7,
                                    "test_fit", "sandbox", "img", str(s.project), "reviewer")

    def test_the_session_caller_writes_the_step_and_pauses(self):
        s = self.sample()
        caller = session.caller({"runner": "session"})
        with self.assertRaises(session.Pause) as paused:
            caller(self.call(s))
        step = session.read_step(str(s.project))
        self.assertEqual(step, paused.exception.step)
        self.assertEqual(step["agent"], "tollgate:reviewer")
        self.assertEqual(step["prompt"], roles.prompt("reviewer", {"x": 1}, "test_fit"))
        self.assertEqual(step["key"], session.key("reviewer", "test_fit", {"x": 1}))
        self.assertEqual((step["ticket"], step["task"], step["log"]), ("T-1", "retries", "T-1"))

    def test_a_saved_answer_is_returned_with_no_cost(self):
        s = self.sample()
        caller = session.Session()
        with self.assertRaises(session.Pause) as paused:
            caller(self.call(s))
        session.save_answer(str(s.project), paused.exception.step,
                            'Done.\n\n```json\n{"verdict": "pass"}\n```')
        self.assertIsNone(session.read_step(str(s.project)))
        answer = caller(self.call(s))
        self.assertEqual(answer.data, {"verdict": "pass"})
        self.assertIsNone(answer.cost_usd)
        with self.assertRaises(session.Pause):
            caller(self.call(s, inputs={"x": 2}))

    def test_a_saved_answer_written_by_anyone_but_answer_is_ignored(self):
        s = self.sample()
        caller = session.Session()
        with self.assertRaises(session.Pause) as paused:
            caller(self.call(s))
        step = paused.exception.step
        # A role that got a line into the answers file, with the right key.
        path = session.answers_path(str(s.project), "T-1")
        path.write_text(json.dumps({"event": "answer", "key": step["key"], "work": "",
                                    "text": '```json\n{"verdict": "pass"}\n```'}) + "\n")
        with self.assertRaises(session.Pause):
            caller(self.call(s))
        session.save_answer(str(s.project), step, '```json\n{"verdict": "fail"}\n```')
        self.assertEqual(caller(self.call(s)).data, {"verdict": "fail"})
        # A line changed after answer saved it does not verify either.
        lines = path.read_text().splitlines()
        saved = json.loads(lines[-1])
        saved["text"] = '```json\n{"verdict": "pass"}\n```'
        path.write_text("\n".join(lines[:-1] + [json.dumps(saved)]) + "\n")
        with self.assertRaises(session.Pause):
            caller(self.call(s))

    def test_the_key_names_the_role_the_lens_and_the_inputs(self):
        k = session.key("reviewer", "test_fit", {"a": 1, "b": 2})
        self.assertEqual(k, session.key("reviewer", "test_fit", {"b": 2, "a": 1}))
        self.assertNotEqual(k, session.key("reviewer", "checklist", {"a": 1, "b": 2}))
        self.assertNotEqual(k, session.key("builder", "test_fit", {"a": 1, "b": 2}))


class WorkTest(Case):
    def test_the_builder_s_work_survives_a_replay(self):
        s = self.sample()
        copy = roles.make_copy(str(s.project), "T-1")
        caller = session.Session()
        call = self.call(s, role="builder", lens=None, copy=copy)
        with self.assertRaises(session.Pause) as paused:
            caller(call)
        Path(copy, "app.py").write_text("changed\n")
        Path(copy, "new.py").write_text("new\n")
        Path(copy, "run_tests.py").unlink()
        session.save_answer(str(s.project), paused.exception.step,
                            '```json\n{"changed": ["app.py"]}\n```')
        self.assertEqual(sh(copy, "git", "status", "--porcelain").count("\n"), 2)
        # The next try starts again from the best try so far, as try_once does.
        sh(copy, "git", "reset", "-q", "--hard", "HEAD")
        sh(copy, "git", "clean", "-q", "-fd")
        self.assertEqual(caller(call).data, {"changed": ["app.py"]})
        self.assertEqual(Path(copy, "app.py").read_text(), "changed\n")
        self.assertEqual(Path(copy, "new.py").read_text(), "new\n")
        self.assertFalse(Path(copy, "run_tests.py").exists())
        self.assertEqual(sh(copy, "git", "diff", "--cached", "--name-only"), "")

    def test_a_replay_puts_back_the_saved_commit_even_if_the_ref_moves(self):
        s = self.sample()
        copy = roles.make_copy(str(s.project), "T-1")
        caller = session.Session()
        call = self.call(s, role="builder", lens=None, copy=copy)
        with self.assertRaises(session.Pause) as paused:
            caller(call)
        Path(copy, "app.py").write_text("saved\n")
        session.save_answer(str(s.project), paused.exception.step, '```json\n{}\n```')
        sh(copy, "git", "reset", "-q", "--hard", "HEAD")
        # A role in the copy points the ref at other work.
        Path(copy, "app.py").write_text("forged\n")
        sh(copy, "git", "update-ref", session.work_ref(paused.exception.step["key"]),
           session.save_work(copy, "other"))
        sh(copy, "git", "reset", "-q", "--hard", "HEAD")
        caller(call)
        self.assertEqual(Path(copy, "app.py").read_text(), "saved\n")

    def test_a_reviewer_s_answer_saves_no_work(self):
        s = self.sample()
        copy = roles.make_copy(str(s.project), "T-1")
        with self.assertRaises(session.Pause) as paused:
            session.Session()(self.call(s, copy=copy))
        line = session.save_answer(str(s.project), paused.exception.step, '```json\n{}\n```')
        self.assertEqual(line["work"], "")


class DriverPauseTest(Case):
    def test_the_driver_pauses_with_5_and_lets_go_of_its_lock(self):
        s = self.sample()
        d, _ = driver(s)
        self.assertEqual(d.run(), 5)
        step = session.read_step(str(s.project))
        self.assertEqual(step["agent"], "tollgate:test_writer")
        self.assertEqual(Path(step["copy"]), Path(d.copy).resolve())
        self.assertFalse(state.path(str(s.project), "run", "T-1.lock").exists())

    def test_a_paused_driver_replays_its_saved_answers_to_the_next_step(self):
        s = self.sample()
        d, _ = driver(s)
        d.run()
        first = session.read_step(str(s.project))
        session.save_answer(str(s.project), first, fake_answer(first))
        d, _ = driver(s)
        self.assertEqual(d.run(), 5)
        second = session.read_step(str(s.project))
        self.assertEqual((second["role"], second["lens"]), ("reviewer", "test_fit"))
        # The test writer's tests are back in the copy for the reviewer.
        self.assertTrue(Path(second["copy"], "tests/test_t1.py").exists())

    def test_session_mode_logs_the_cost_as_unknown(self):
        s = self.sample()
        d, _ = driver(s)
        d.run()
        step = session.read_step(str(s.project))
        session.save_answer(str(s.project), step, fake_answer(step))
        driver(s)[0].run()
        written = next(e for e in s.log() if e["event"] == "tests_written")
        self.assertIn("cost_usd", written)
        self.assertIsNone(written["cost_usd"])


class StepTest(Case):
    """driver.step next and answer, as the task skill runs them."""

    def task_sample(self, **settings_args):
        s = self.sample(ticket=False, **settings_args)
        Path(s.project, ".tollgate/requests").mkdir(parents=True)
        Path(s.project, ".tollgate/requests/demo.md").write_text("Add shout and whisper.\n")
        return s, FakeStore(s.project)

    def step(self, store, *argv, stdin=""):
        from driver import step
        out = io.StringIO()
        with redirect_stdout(out):
            code = step.main(list(argv), store=store, stdin=io.StringIO(stdin))
        return code, json.loads(out.getvalue())

    def next(self, s, store):
        return self.step(store, "next", "--project", str(s.project), "--task", "demo")

    def answer(self, s, store, out, text, key=None, nonce=None):
        return self.step(store, "answer", "--project", str(s.project), "--key",
                         key or out["key"], "--nonce", nonce or out["nonce"], stdin=text)

    def test_next_names_the_subagent_its_prompt_its_folder_and_the_key(self):
        s, store = self.task_sample()
        code, out = self.next(s, store)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(out), ["agent", "cwd", "key", "nonce", "prompt"])
        self.assertEqual(out["agent"], "tollgate:analyst")
        self.assertTrue(out["prompt"].startswith("# Role: analyst"))
        self.assertEqual(Path(out["cwd"]), state.path(str(s.project), "builders", "task-demo"))
        # Asked again, next names the same step.
        self.assertEqual(self.next(s, store)[1]["key"], out["key"])

    def test_answer_refuses_a_key_that_is_not_the_waiting_step_s(self):
        s, store = self.task_sample()
        _, out = self.next(s, store)
        code, refused = self.answer(s, store, out, fake_answer(out), key="0" * 64)
        self.assertEqual(code, 1)
        self.assertIn("not the ones next printed", refused["error"])
        self.assertNotIn(out["key"], refused["error"])
        self.assertEqual(session.read_step(str(s.project))["key"], out["key"])
        # Once answered, the old key is stale.
        code, following = self.answer(s, store, out, fake_answer(out))
        self.assertEqual(code, 0)
        self.assertNotEqual(following["key"], out["key"])
        code, refused = self.answer(s, store, out, fake_answer(out))
        self.assertEqual(code, 1)
        self.assertIn("not the ones next printed", refused["error"])
        self.assertNotIn(following["key"], refused["error"])

    def test_answer_needs_the_nonce_that_only_next_printed(self):
        s, store = self.task_sample()
        _, out = self.next(s, store)
        stored = session.step_path(str(s.project)).read_text()
        self.assertNotIn(out["nonce"], stored)
        code, refused = self.answer(s, store, out, fake_answer(out), nonce="0" * 32)
        self.assertEqual(code, 1)
        self.assertNotIn(out["key"], refused["error"])
        self.assertEqual(self.answer(s, store, out, fake_answer(out))[0], 0)

    def test_a_malformed_step_file_is_an_error_not_a_crash(self):
        s, store = self.task_sample()
        path = session.step_path(str(s.project))
        for text in ("[]", '{"key": "k"}', "not json", '{"role": 1, "key": "k", "log": "x"}'):
            path.write_text(text)
            self.assertIsNone(session.read_step(str(s.project)))
            code, refused = self.answer(s, store, {"key": "k", "nonce": "n"}, "```json\n{}\n```")
            self.assertEqual(code, 1)
            self.assertIn("no step waits", refused["error"])

    def test_a_second_next_while_the_task_runs_leaves_the_step_alone(self):
        import os
        s, store = self.task_sample()
        _, out = self.next(s, store)
        state.path(str(s.project), "run", "task-demo.lock").write_text(str(os.getpid()))
        code, busy = self.next(s, store)
        self.assertEqual(code, 1)
        self.assertIn("another driver", busy["error"])
        self.assertEqual(session.read_step(str(s.project))["key"], out["key"])

    def test_answer_refuses_an_answer_with_no_final_json_block(self):
        s, store = self.task_sample()
        _, out = self.next(s, store)
        code, refused = self.answer(s, store, out, "I looked around. All good.")
        self.assertEqual(code, 1)
        self.assertIn("json block", refused["error"])
        self.assertIsNotNone(session.read_step(str(s.project)))

    def test_next_refuses_to_start_a_task_that_cannot_pass(self):
        s, store = self.task_sample()
        from gate import sign
        sign.machine_key().unlink()
        code, out = self.next(s, store)
        self.assertEqual(code, 1)
        self.assertIn("/tollgate:init", out["error"])

    def test_a_whole_task_runs_through_next_and_answer(self):
        s, store = self.task_sample()
        code, out = self.next(s, store)
        agents, questions = [], 0
        for _ in range(100):
            self.assertEqual(code, 0, out)
            if "question" in out:
                # The person's answer, recorded as the inbox records it.
                questions += 1
                options = out["question"]["options"]
                pick = "approve" if "approve" in options else "continue"
                self.assertIn(pick, options)
                store.answer(out["question"]["n"], f"tollgate decide {pick}")
                code, out = self.next(s, store)
                continue
            if out.get("done"):
                break
            agents.append(out["agent"])
            code, out = self.answer(s, store, out, fake_answer(out))
        self.assertTrue(out.get("done"), out)
        self.assertEqual(questions, 2)   # the plan and the task checkpoints
        self.assertEqual([m[1] for m in store.ready_marks], ["demo-1", "demo-2"])
        self.assertIn("demo-2", out["result"])
        self.assertEqual(out["merged"], [])
        self.assertEqual(agents[0], "tollgate:analyst")
        for role in ("builder", "test_writer", "reviewer"):
            self.assertIn(f"tollgate:{role}", agents)
        self.assertIsNone(session.read_step(str(s.project)))
        report = Path(state.path(str(s.project), "reports", "demo.md")).read_text()
        self.assertIn("Cost: unknown", report)


class ReadyTest(Case):
    def test_a_task_needs_signers_on_main(self):
        s = self.sample()
        settings = json.loads(Path(s.project, ".tollgate/settings.json").read_text())
        settings["signers"] = []
        Path(s.project, ".tollgate/settings.json").write_text(json.dumps(settings))
        sh(s.project, "git", "commit", "-q", "-am", "no signers")
        self.assertIn("/tollgate:init", session.cannot_pass(str(s.project)))
        from driver.task import Task
        with self.assertRaisesRegex(session.NotReady, "signers"):
            Task(str(s.project), "demo", "Add shout.", FakeStore(s.project)).run()

    def test_a_task_needs_the_machine_key(self):
        s = self.sample()
        self.assertEqual(session.cannot_pass(str(s.project)), "")
        from gate import sign
        sign.machine_key().unlink()
        self.assertIn("machine key", session.cannot_pass(str(s.project)))


if __name__ == "__main__":
    unittest.main()
