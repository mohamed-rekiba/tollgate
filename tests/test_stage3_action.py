"""Tests for the plan format, the plan tag, and the review on the server."""

import unittest

from action import manifest as mf
from action import plan as pl
from action import plantag, review
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


class ServerReviewTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(".tollgate/settings.json",
                        settings_text(tiers={"3": ["src/auth/**"]}))
        self.repo.commit("main")
        self.repo.git("checkout", "-q", "-b", "tg/T-1")

    def change(self, path):
        self.repo.write(path, "x = 1\n")
        self.repo.commit("change")

    def test_tier_1_passes_without_a_model(self):
        self.change("src/a.py")
        passed, title, _ = review.review(str(self.repo.path), "main", "HEAD", "tg/T-1", key="")
        self.assertTrue(passed)
        self.assertEqual(title, "Not needed for tier 1.")

    def test_tier_3_with_no_key_fails(self):
        self.change("src/auth/login.py")
        passed, title, text = review.review(str(self.repo.path), "main", "HEAD", "tg/T-1", key="")
        self.assertFalse(passed)
        self.assertIn("no model access", title)
        self.assertIn("ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN", text)

    def test_tier_3_runs_both_lenses_and_fails_on_a_blocking_finding(self):
        self.change("src/auth/login.py")
        seen = []

        def fake(lens, inputs):
            seen.append(lens)
            self.assertIn("src/auth/login.py", inputs["diff"])
            if lens == "security":
                return {"verdict": "fail", "findings": [
                    {"level": "blocking", "file": "src/auth/login.py", "line": 1,
                     "text": "the login check is gone"}]}
            return {"verdict": "pass", "findings": []}

        passed, _, text = review.review(str(self.repo.path), "main", "HEAD", "tg/T-1", fake)
        self.assertEqual(seen, ["change", "security"])
        self.assertFalse(passed)
        self.assertIn("the login check is gone", text)

    def test_tier_3_passes_when_no_finding_blocks(self):
        self.change("src/auth/login.py")
        passed, title, _ = review.review(
            str(self.repo.path), "main", "HEAD", "tg/T-1",
            lambda lens, inputs: {"verdict": "pass", "findings": [{"level": "minor", "text": "x"}]})
        self.assertTrue(passed)
        self.assertEqual(title, "Passed. Tier 3.")

    def test_tier_only_output(self):
        self.change("src/auth/login.py")
        import tempfile
        with tempfile.NamedTemporaryFile("r") as f:
            review.main(["--repo", str(self.repo.path), "--base", "main", "--head", "HEAD",
                         "--branch", "tg/T-1", "--tier-out", f.name])
            self.assertEqual(f.read(), "3")



if __name__ == "__main__":
    unittest.main()
