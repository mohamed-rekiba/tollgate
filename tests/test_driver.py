"""Tests for the log, the run lock, and the score. The loop is in test_driver_loop.py,
the role runner in test_roles.py."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from driver.driver import Busy, TicketLock, score
from driver.log import Log, LogBusy, read
from gate import tickets
from tests.fakes import TICKET


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

    def test_a_held_event_is_written_once_unless_the_file_has_it(self):
        # A replay holds its events. Those an earlier run logged are not written again;
        # the rest are written when the hold ends or the log closes, in order.
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.jsonl")
            with Log(path) as log:
                log.add("a")
                log.add("b", n=1)
            quiet = [True]
            with Log(path) as log:
                log.hold_while(lambda: quiet[0])
                log.add("a")
                log.add("b", n=1)
                log.add("b", n=1)
                log.add("c")
                self.assertEqual([e["event"] for e in read(path)], ["a", "b"])
                quiet[0] = False
                log.add("d")
            with Log(path) as log:
                log.hold_while(lambda: True)
                log.add("d")
                log.add("e")
            events = [(e["event"], e.get("n")) for e in read(path)]
        self.assertEqual(events, [("a", None), ("b", 1), ("b", 1), ("c", None), ("d", None),
                                  ("e", None)])

    def test_a_torn_last_line_is_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.jsonl")
            Path(path).write_text('{"event": "a"}\n{"event": "b"')
            self.assertEqual([e["event"] for e in read(path)], ["a"])


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





class AnswerTest(unittest.TestCase):
    def test_a_structured_answer_and_a_typed_answer_both_count(self):
        from driver.advisor import parse_answer
        self.assertEqual(parse_answer({"decision": "retry", "hint": "smaller", "at": "x"}),
                         {"decision": "retry", "hint": "smaller"})
        self.assertEqual(parse_answer("tollgate decide park too large\nmore"),
                         {"decision": "park", "hint": "too large"})

    def test_no_answer_is_no_decision(self):
        from driver.advisor import parse_answer
        for answer in (None, "", {"decision": ""}, "Retry!"):
            self.assertIsNone(parse_answer(answer), answer)

if __name__ == "__main__":
    unittest.main()
