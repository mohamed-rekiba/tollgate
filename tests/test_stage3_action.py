"""Tests for the plan format, the plan tag, and the review."""

import unittest

from gate import manifest as mf
from gate import plan as pl
from gate import plantag, review
from tests.helpers import TICKET, Repo, settings_text

PLAN = """---
id: retries
tickets: T-1
---
## Task
Retry failed deliveries.

## Design
Wrap the sender in a loop with a fixed wait.

## Files
src/retry.py

## Seams
POST /deliver

## Tickets
- T-1: retry a failed delivery up to three times.
"""


class PlanFormatTest(unittest.TestCase):
    def test_reads_a_plan(self):
        p = pl.parse(PLAN)
        self.assertEqual((p.id, p.tickets), ("retries", ["T-1"]))
        self.assertIn("loop", p.sections["Design"])

    def test_reads_a_bracketed_ticket_list_and_leading_blank_lines(self):
        p = pl.parse("\n\n" + PLAN.replace("tickets: T-1", "tickets: [T-1]"))
        self.assertEqual(p.tickets, ["T-1"])

    def test_refuses_a_plan_with_a_missing_section(self):
        with self.assertRaisesRegex(pl.PlanError, "Seams"):
            pl.parse(PLAN.replace("## Seams\nPOST /deliver\n", ""))

    def test_refuses_a_ticket_the_tickets_section_does_not_describe(self):
        with self.assertRaisesRegex(pl.PlanError, "does not describe T-2"):
            pl.parse(PLAN.replace("tickets: T-1", "tickets: T-1, T-2"))

    def test_checks_that_each_ticket_names_the_plan(self):
        p = pl.parse(PLAN)
        self.assertEqual(pl.check_tickets(p, lambda path: TICKET.replace("plan: retries",
                                                                           "plan: other")),
                         ["ticket T-1 names plan other, not retries"])
        self.assertEqual(pl.check_tickets(p, lambda path: None), ["ticket T-1 has no file"])


class PlanTagTest(unittest.TestCase):
    def test_builds_the_tag_message(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(pl.plan_path("retries"), PLAN)
        repo.write(mf.ticket_path("T-1"), TICKET)
        commit = repo.commit()
        name, text = plantag.message(str(repo.path), "retries", commit, "7")
        self.assertEqual(name, "tg/plan/retries/1")
        body = mf.loads(text)
        self.assertEqual((body["tickets"], body["run_id"], body["number"]), (["T-1"], 7, 1))
        self.assertEqual(sorted(body["files"]), sorted([mf.ticket_path("T-1"), pl.plan_path("retries")]))

    def test_refuses_a_plan_whose_ticket_file_is_missing(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(pl.plan_path("retries"), PLAN)
        commit = repo.commit()
        with self.assertRaisesRegex(pl.PlanError, "T-1 has no file"):
            plantag.message(str(repo.path), "retries", commit, "7")


class LocalReviewTest(unittest.TestCase):
    def test_tier_1_and_2_pass_without_the_reviewer(self):
        def never(lens, inputs):
            raise AssertionError("the reviewer ran")
        for level in (1, 2):
            passed, findings, text = review.review(level, TICKET, "diff", never)
            self.assertEqual((passed, findings), (True, []))
            self.assertEqual(text, f"Not needed for tier {level}.")

    def test_tier_3_runs_both_lenses_and_fails_on_a_blocking_finding(self):
        seen = []

        def fake(lens, inputs):
            seen.append(lens)
            self.assertEqual(inputs["diff"], "the diff")
            if lens == "security":
                return {"verdict": "fail", "findings": [
                    {"level": "blocking", "file": "src/auth/login.py", "line": 1,
                     "text": "the login check is gone"}]}
            return {"verdict": "pass", "findings": []}

        passed, findings, text = review.review(3, TICKET, "the diff", fake)
        self.assertEqual(seen, ["change", "security"])
        self.assertFalse(passed)
        self.assertEqual(findings[0]["lens"], "security")
        self.assertIn("the login check is gone", text)

    def test_a_fail_verdict_with_no_blocking_finding_still_fails(self):
        passed, _, _ = review.review(4, TICKET, "d", lambda lens, i: {"verdict": "fail"})
        self.assertFalse(passed)

    def test_tier_3_passes_when_no_finding_blocks(self):
        passed, _, text = review.review(
            3, TICKET, "d",
            lambda lens, inputs: {"verdict": "pass", "findings": [{"level": "minor", "text": "x"}]})
        self.assertTrue(passed)
        self.assertTrue(text.startswith("Passed. Tier 3."))

    def test_the_diff_is_the_change_from_main(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(".tollgate/settings.json", settings_text())
        repo.commit("main")
        repo.git("checkout", "-q", "-b", "tg/T-1")
        repo.write("src/auth/login.py", "x = 1\n")
        repo.commit("change")
        self.assertIn("src/auth/login.py", review.diff(str(repo.path), "main", "HEAD"))


if __name__ == "__main__":
    unittest.main()
