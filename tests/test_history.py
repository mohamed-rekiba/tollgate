"""Tests for what a log says: one replay of a ticket's events."""

import unittest

from driver import history


def ev(event, **fields):
    return {"at": "2026-11-21T10:00:00Z", "ticket": "shop-1", "task": "shop", "event": event,
            **fields}


class ReplayTest(unittest.TestCase):
    def test_an_empty_log_is_not_started(self):
        t = history.replay([])
        self.assertEqual((t.state, t.attempts, t.best_score, t.pr), ("not started", 0, -1, 0))

    def test_the_best_attempt_and_the_last_failure(self):
        t = history.replay([
            ev("frozen", tag="tg/freeze/shop-1/1", commit="c0"),
            ev("attempt_failed", attempt=1, commit="c1", score=60, tier=2,
               failed_key=[["tests"], []]),
            ev("attempt_failed", attempt=2, commit="c2", score=40, tier=2,
               failed_key=[[], ["t::a"]]),
        ])
        self.assertEqual((t.ticket, t.task, t.state), ("shop-1", "shop", "building"))
        self.assertEqual((t.attempts, t.best_score, t.best_commit), (2, 60, "c1"))
        self.assertEqual(t.last_failed, ((), ("t::a",)))
        self.assertEqual((t.frozen, t.tier, t.passed_commit), ("tg/freeze/shop-1/1", 2, ""))

    def test_a_pass_then_a_pull_request(self):
        t = history.replay([ev("frozen", tag="x", commit="c0"),
                            ev("attempt_passed", attempt=1, commit="c1", score=90),
                            ev("pr_opened", pr=12)])
        self.assertEqual((t.state, t.passed_commit, t.pr), ("pull request open", "c1", 12))

    def test_advisor_decisions(self):
        t = history.replay([ev("advisor_decided", by="ai", decision="retry", hint="smaller"),
                            ev("advisor_decided", by="person", decision="stronger", hint="")])
        self.assertEqual((t.ai_decisions, t.extra_attempts, t.stronger), (1, 2, True))

    def test_the_reason_comes_from_the_last_stop(self):
        t = history.replay([ev("parked", reason="too large"),
                            ev("waiting_for_advisor", reason="the same checks failed", issue=4)])
        self.assertEqual((t.state, t.reason), ("waits for a person", "the same checks failed"))

    def test_tests_reviewed_and_rejected(self):
        t = history.replay([ev("tests_rejected"), ev("tests_rejected"), ev("tests_reviewed")])
        self.assertEqual((t.rejections, t.tests_done, t.state), (2, True, "tests written"))


class OpenQuestionTest(unittest.TestCase):
    def test_an_unanswered_question(self):
        events = [ev("waiting_for_advisor", issue=4, reason="stuck")]
        self.assertEqual(history.open_question(events), {"issue": 4, "reason": "stuck"})

    def test_a_question_a_person_answered(self):
        events = [ev("waiting_for_advisor", issue=4, reason="stuck"),
                  ev("advisor_decided", by="person", issue=4, decision="retry")]
        self.assertIsNone(history.open_question(events))

    def test_no_question(self):
        self.assertIsNone(history.open_question([ev("waiting_for_advisor", by="ai")]))


class CostAndMinutesTest(unittest.TestCase):
    def test_cost_and_minutes(self):
        events = [dict(ev("a", cost_usd=0.5), at="2026-11-21T10:00:00Z"),
                  dict(ev("b", cost_usd=None), at="2026-11-21T10:31:00Z"),
                  dict(ev("c", cost_usd="0.25"), at="2026-11-21T10:44:00Z")]
        self.assertEqual((history.cost(events), history.minutes(events)), (0.75, 44))
        self.assertEqual((history.cost([]), history.minutes([])), (0, 0))


if __name__ == "__main__":
    unittest.main()
