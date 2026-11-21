"""Tests for the stop rules: one case that goes on and one that stops, for each rule."""

import unittest

from driver import stop

SETTINGS = {"stop": {"attempts": 3, "attempt_minutes": 30, "ticket_usd": 10, "task_usd": 60}}


def failed(n, checks=(), tests=(), score=-1, items=None, **fields):
    return {"event": "try_failed", "attempt": n, "failed_key": [list(checks), list(tests)],
            "score": score, "items": items or {}, **fields}


def retry():
    return {"event": "advisor_decided", "by": "ai", "decision": "retry"}


class TriesTest(unittest.TestCase):
    def test_two_tries_go_on(self):
        events = [failed(1, tests=["a"]), failed(2, tests=["b"])]
        self.assertEqual(stop.check(events, SETTINGS), stop.GO)

    def test_three_tries_stop(self):
        events = [failed(1, tests=["a"]), failed(2, tests=["b"]), failed(3, tests=["c"])]
        self.assertEqual(stop.check(events, SETTINGS), "stop: the ticket used 3 tries")

    def test_a_retry_grants_one_more_try(self):
        events = [failed(1, tests=["a"]), failed(2, tests=["b"]), failed(3, tests=["c"]), retry()]
        self.assertEqual(stop.check(events, SETTINGS), stop.GO)
        events.append(failed(4, tests=["d"]))
        self.assertEqual(stop.check(events, SETTINGS), "stop: the ticket used 4 tries")


class SameFailureTest(unittest.TestCase):
    def test_different_checks_go_on(self):
        events = [failed(1, checks=["tests"], tests=["a"]), failed(2, checks=["tests"], tests=["b"])]
        self.assertEqual(stop.check(events, SETTINGS), stop.GO)

    def test_the_same_checks_twice_stop(self):
        events = [failed(1, checks=["tests"], tests=["a"]), failed(2, checks=["tests"], tests=["a"])]
        self.assertTrue(stop.check(events, SETTINGS).startswith(
            "stop: try 2 failed the same way as the try before it: checks tests, a"))

    def test_the_same_items_at_another_score_go_on(self):
        events = [failed(1, score=67, items={"C1": True, "C3": False}),
                  failed(2, score=50, items={"C1": True, "C3": False})]
        self.assertEqual(stop.check(events, SETTINGS), stop.GO)

    def test_the_same_items_at_the_same_score_stop(self):
        events = [failed(1, score=67, items={"C1": True, "C3": False}),
                  failed(2, score=67, items={"C1": True, "C3": False})]
        self.assertEqual(stop.check(events, SETTINGS), "stop: try 2 failed the same way as the "
                                                       "try before it: items C3 at score 67")

    def test_after_a_retry_the_old_pair_does_not_count(self):
        events = [failed(1, tests=["a"]), failed(2, tests=["a"]), retry()]
        self.assertEqual(stop.check(events, SETTINGS), stop.GO)


class TimeTest(unittest.TestCase):
    def test_a_short_try_goes_on(self):
        self.assertEqual(stop.check([failed(1, tests=["a"], seconds=60)], SETTINGS), stop.GO)

    def test_a_try_past_30_minutes_stops(self):
        self.assertEqual(stop.check([failed(1, tests=["a"], seconds=1800)], SETTINGS),
                         "stop: try 1 ran past 30 minutes")
        self.assertEqual(stop.check([failed(1, timed_out=True)], SETTINGS),
                         "stop: try 1 ran past 30 minutes")


class CostTest(unittest.TestCase):
    def test_under_10_usd_goes_on(self):
        self.assertEqual(stop.check([{"event": "tests_written", "cost_usd": 9.99}], SETTINGS),
                         stop.GO)

    def test_10_usd_for_a_ticket_stops_hard(self):
        verdict = stop.check([{"event": "tests_written", "cost_usd": 10}], SETTINGS)
        self.assertEqual(verdict, "stop: the ticket cost 10.0 USD; the limit is 10 USD")
        self.assertTrue(stop.is_hard(verdict))

    def test_under_60_usd_for_a_task_goes_on(self):
        self.assertEqual(stop.check([], SETTINGS, task_spent=59.9), stop.GO)

    def test_60_usd_for_a_task_stops_hard(self):
        verdict = stop.check([], SETTINGS, task_spent=60)
        self.assertEqual(verdict, "stop: the task cost 60 USD; the limit is 60 USD")
        self.assertTrue(stop.is_hard(verdict))
        self.assertFalse(stop.is_hard("stop: the ticket used 3 tries"))

    def test_every_number_comes_from_the_settings(self):
        tight = {"stop": {"attempts": 1, "attempt_minutes": 1, "ticket_usd": 1, "task_usd": 2}}
        self.assertEqual(stop.check([failed(1, tests=["a"])], tight),
                         "stop: the ticket used 1 try")
        self.assertTrue(stop.check([failed(1, seconds=61)], tight).endswith("ran past 1 minutes"))
        self.assertTrue(stop.check([{"event": "x", "cost_usd": 1}], tight).startswith(
            "stop: the ticket cost"))
        self.assertTrue(stop.check([], tight, task_spent=2).startswith("stop: the task cost"))


if __name__ == "__main__":
    unittest.main()
