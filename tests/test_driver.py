"""Tests for the log, the role runner, the ticket lock, and the score."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from action import tickets
from driver import roles
from driver.driver import Busy, TicketLock, score
from driver.log import Log, LogBusy, read
from tests.fakes import FAKE_ROLE, TICKET


class LogTest(unittest.TestCase):
    def test_lines_read_back_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "logs", "T-1.jsonl")
            with Log(path, ticket="T-1") as log:
                log.add("a", n=1)
                log.add("b", n=2)
            events = read(path)
        self.assertEqual([e["event"] for e in events], ["a", "b"])
        self.assertEqual(events[0]["ticket"], "T-1")

    def test_a_second_writer_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.jsonl")
            root = str(Path(__file__).resolve().parent.parent)
            code = (f"import sys,time; sys.path.insert(0, {root!r}); from driver.log import Log; "
                    f"held = Log({path!r}); print('held', flush=True); time.sleep(20)")
            other = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                     text=True)
            try:
                self.assertEqual(other.stdout.readline().strip(), "held")
                with self.assertRaises(LogBusy):
                    Log(path)
            finally:
                other.kill()
                other.wait()
                other.stdout.close()

    def test_a_torn_last_line_is_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.jsonl")
            Path(path).write_text('{"event": "a"}\n{"event": "b"')
            self.assertEqual([e["event"] for e in read(path)], ["a"])


class RolesTest(unittest.TestCase):
    def test_reads_the_last_json_block(self):
        text = 'x\n```json\n{"a": 1}\n```\nthen\n```json\n{"a": 2}\n```\n'
        self.assertEqual(roles.last_block(text), {"a": 2})
        with self.assertRaises(roles.RoleError):
            roles.last_block("no block")

    def test_claude_gets_its_flags_and_a_fake_does_not(self):
        args = roles.command_line("claude -p", "reviewer")
        self.assertEqual(args[-4:], ["--output-format", "json", "--allowedTools",
                                     "Read,Grep,Glob"])
        self.assertEqual(roles.command_line("python3 fake.py x", "builder"),
                         ["python3", "fake.py", "x"])

    def test_container_gets_whichever_model_access_is_set(self):
        saved = {k: os.environ.pop(k, None) for k in roles.MODEL_ACCESS}
        try:
            os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "t"
            os.environ["ANTHROPIC_API_KEY"] = ""
            args = roles.command_line("claude -p", "builder", "container", "img:1", "/w")
            self.assertIn("CLAUDE_CODE_OAUTH_TOKEN", args)
            self.assertNotIn("ANTHROPIC_API_KEY", args)
            roles.drop_empty_access()
            self.assertNotIn("ANTHROPIC_API_KEY", os.environ)
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_container_mounts_only_the_copy_and_no_credentials(self):
        args = roles.command_line("claude -p", "builder", "container", "img:1", "/w")
        self.assertEqual(args[:3], ["docker", "run", "--rm"])
        joined = " ".join(args)
        self.assertIn("/w:/work", joined)
        self.assertNotIn(".ssh", joined)
        self.assertNotIn("gh", args[: args.index("img:1")])
        self.assertNotIn("GH_TOKEN", joined)
        with self.assertRaises(roles.RoleError):
            roles.command_line("claude -p", "builder", "container", "", "/w")

    def test_runs_a_fake_role_and_reads_the_cost(self):
        with tempfile.TemporaryDirectory() as d:
            answer = roles.run(f"{sys.executable} {FAKE_ROLE} ok cost=0.25", "advisor",
                               {"reason": "x"}, d, 1)
        self.assertEqual(answer.data["decision"], "park")
        self.assertEqual(answer.cost_usd, 0.25)

    def test_a_failing_role_shows_what_it_printed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(roles.RoleError, "credit balance is too low"):
                roles.run(f"{sys.executable} -c 'print(\"credit balance is too low\"); exit(1)'",
                          "reviewer", {}, d, 1)
            with self.assertRaisesRegex(roles.RoleError, "reported an error: bad key"):
                roles.run(f"{sys.executable} -c 'import json; print(json.dumps("
                          f"{{\"is_error\": True, \"result\": \"bad key\"}}))'",
                          "reviewer", {}, d, 1)

    def test_a_role_past_its_time_fails(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(roles.RoleError, "ran past"):
            roles.run(f"{sys.executable} -c 'import time; time.sleep(5)'", "builder", {}, d, 0.01)

    def test_copy_is_fresh_and_removed(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            path = roles.make_copy(d, "T-1")
            self.assertTrue(Path(path, ".git").exists())
            roles.remove_copy(d, "T-1")
            self.assertFalse(Path(path).exists())


class PushTest(unittest.TestCase):
    def test_on_github_the_token_goes_to_the_push_command_only(self):
        import subprocess as sp
        from unittest import mock

        from driver import driver as drv
        calls = []

        def fake_run(args, **kw):
            calls.append(args)
            return sp.CompletedProcess(args, 0, "", "")
        env = {"GITHUB_ACTIONS": "true", "GH_TOKEN": "abc"}
        with mock.patch.dict(os.environ, env), mock.patch.object(drv.subprocess, "run", fake_run):
            drv.push(".", "origin", "HEAD:refs/heads/x")
            drv.git(".", "fetch", "-q", "origin")
            drv.git(".", "status")
        self.assertTrue(calls[0][2].startswith("http.extraheader=AUTHORIZATION: basic "))
        self.assertEqual(calls[0][3:], ["push", "origin", "HEAD:refs/heads/x"])
        self.assertEqual(calls[1][3], "fetch")
        self.assertEqual(calls[2], ["git", "status"])
        calls.clear()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}), mock.patch.object(
                drv.subprocess, "run", fake_run):
            drv.push(".", "origin", "x")
        self.assertEqual(calls[0], ["git", "push", "origin", "x"])

    def test_on_github_opening_a_pull_request_starts_the_gate(self):
        from unittest import mock

        from driver.server import GitHub
        made = []

        class Gh:
            def get(self, path):
                return []

            def api(self, method, path, body=None):
                made.append((method, path, body))
                return {"number": 41}
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            self.assertEqual(GitHub("o/r", gh=Gh()).open_pr("tg/T-1", "t", "b"), 41)
        self.assertEqual(made[-1][2], {"ref": "main", "inputs": {"kind": "check", "id": "41"}})
        made.clear()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": ""}):
            GitHub("o/r", gh=Gh()).open_pr("tg/T-1", "t", "b")
        self.assertEqual(len(made), 1)


class LockTest(unittest.TestCase):
    def test_a_live_holder_refuses_and_a_dead_one_is_taken_over(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "run", "T-1.lock")
            os.makedirs(os.path.dirname(path))
            sleeper = subprocess.Popen(["sleep", "30"])
            try:
                Path(path).write_text(str(sleeper.pid))
                with self.assertRaises(Busy):
                    TicketLock(path).acquire()
            finally:
                sleeper.kill()
                sleeper.wait()
            TicketLock(path).acquire().release()
            self.assertFalse(os.path.exists(path))


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.ticket = tickets.parse(TICKET)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, "app.py").write_text("a\nb\nc\n")

    def test_share_of_passed_items(self):
        tests = {"t::test_c1_shout": "passed", "t::test_c2_greet_kept": "passed"}
        value, passed = score(self.ticket, tests,
                              [{"item": "C3", "passed": True, "file": "app.py", "line": 3}],
                              self.tmp.name)
        self.assertEqual((value, passed), (100, {"C1": True, "C2": True, "C3": True}))
        tests["t::test_c1_shout"] = "failed"
        value, _ = score(self.ticket, tests, [{"item": "C3", "passed": True, "file": "app.py",
                                               "line": 3}], self.tmp.name)
        self.assertEqual(value, round(100 * 2 / 3))

    def test_a_line_that_does_not_exist_is_a_fail(self):
        tests = {"t::test_c1_shout": "passed", "t::test_c2_greet_kept": "passed"}
        for claim in ({"item": "C3", "passed": True, "file": "app.py", "line": 4},
                      {"item": "C3", "passed": True, "file": "nope.py", "line": 1},
                      {"item": "C3", "passed": True, "file": "../app.py", "line": 1},
                      {"item": "C3", "passed": True}):
            value, passed = score(self.ticket, tests, [claim], self.tmp.name)
            self.assertFalse(passed["C3"], json.dumps(claim))
            self.assertEqual(value, 67)


if __name__ == "__main__":
    unittest.main()
