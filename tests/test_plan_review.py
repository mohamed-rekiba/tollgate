"""Tests for the plan format, the plan lock, and the local review."""

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
modify src/retry.py

## Seams
POST /deliver

## Reuse
src/send.py: send, unchanged.

## Risks
- A wait that never ends: the loop stops after three tries.

## Assumptions
none

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

    def test_refuses_a_plan_with_no_reuse_risks_or_assumptions(self):
        for name in ("Reuse", "Risks", "Assumptions"):
            start = PLAN.index(f"## {name}")
            end = PLAN.index("## ", start + 3)
            with self.subTest(section=name), self.assertRaisesRegex(pl.PlanError, name):
                pl.parse(PLAN[:start] + PLAN[end:])

    def test_each_file_says_create_modify_or_delete(self):
        with self.assertRaisesRegex(pl.PlanError, "create, modify, or delete: src/retry.py"):
            pl.parse(PLAN.replace("modify src/retry.py", "src/retry.py"))
        plan = pl.parse(PLAN.replace("modify src/retry.py", "create src/retry.py\ndelete src/old.py"))
        self.assertEqual(plan.files, {"src/retry.py": "create", "src/old.py": "delete"})

    def test_no_assumptions_means_no_questions(self):
        self.assertEqual(pl.parse(PLAN).questions, [])

    def test_each_assumption_asks_a_question(self):
        asks = PLAN.replace("## Assumptions\nnone", "## Assumptions\n- Is three tries enough?\n"
                            "- Should a failure write to the log?")
        self.assertEqual(pl.parse(asks).questions,
                         ["Is three tries enough?", "Should a failure write to the log?"])
        with self.assertRaisesRegex(pl.PlanError, "ask a question: Three tries is enough."):
            pl.parse(PLAN.replace("## Assumptions\nnone", "## Assumptions\n- Three tries is enough."))

    def test_refuses_a_ticket_the_tickets_section_does_not_describe(self):
        with self.assertRaisesRegex(pl.PlanError, "does not describe T-2"):
            pl.parse(PLAN.replace("tickets: T-1", "tickets: T-1, T-2"))

    def test_checks_that_each_ticket_names_the_plan(self):
        p = pl.parse(PLAN)
        self.assertEqual(pl.check_tickets(p, lambda path: TICKET.replace("plan: retries",
                                                                           "plan: other")),
                         ["ticket T-1 names plan other, not retries"])
        self.assertEqual(pl.check_tickets(p, lambda path: None), ["ticket T-1 has no file"])


class PlanLockTest(unittest.TestCase):
    def test_builds_the_plan_lock(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(pl.plan_path("retries"), PLAN)
        repo.write(mf.ticket_path("T-1"), TICKET)
        commit = repo.commit()
        body = plantag.record(str(repo.path), "retries", commit)
        self.assertEqual((body["task"], body["commit"]), ("retries", commit))
        self.assertEqual(sorted(body["files"]), sorted([mf.ticket_path("T-1"), pl.plan_path("retries")]))

    def test_refuses_a_plan_whose_ticket_file_is_missing(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(pl.plan_path("retries"), PLAN)
        commit = repo.commit()
        with self.assertRaisesRegex(pl.PlanError, "T-1 has no file"):
            plantag.record(str(repo.path), "retries", commit)


DIFF = """diff --git a/src/auth/login.py b/src/auth/login.py
--- a/src/auth/login.py
+++ b/src/auth/login.py
@@ -10,3 +10,4 @@ def login(user):
     name = user.name
-    check(user)
+    if user.admin:
+        check(user)
     return name
"""


def finding(level, file, line, text="x"):
    return {"level": level, "file": file, "line": line, "text": text}


class LocalReviewTest(unittest.TestCase):
    def test_tier_1_passes_without_the_reviewer(self):
        def never(lens, inputs):
            raise AssertionError("the reviewer ran")
        passed, findings, text = review.review(1, TICKET, DIFF, never)
        self.assertEqual((passed, findings), (True, []))
        self.assertEqual(text, "Not needed for tier 1.")

    def test_each_tier_runs_its_lenses(self):
        for level, lenses in ((2, ["review"]), (3, ["review", "security"]),
                              (4, ["review", "security"])):
            seen = []
            review.review(level, TICKET, DIFF,
                          lambda lens, inputs, seen=seen: seen.append(lens) or {"verdict": "pass"})
            with self.subTest(tier=level):
                self.assertEqual(seen, lenses)

    def test_tier_3_fails_on_a_blocking_finding_in_the_change(self):
        def fake(lens, inputs):
            self.assertEqual(inputs["diff"], DIFF)
            if lens == "security":
                return {"verdict": "fail", "findings": [
                    finding("blocking", "src/auth/login.py", 12, "the login check is skipped")]}
            return {"verdict": "pass", "findings": []}

        passed, findings, text = review.review(3, TICKET, DIFF, fake)
        self.assertFalse(passed)
        self.assertEqual(findings[0]["lens"], "security")
        self.assertIn("the login check is skipped", text)

    def test_a_finding_outside_the_change_is_dropped(self):
        found = [finding("blocking", "src/auth/login.py", 90),   # a line the change does not touch
                 finding("blocking", "src/other.py", 1),         # a file the change does not touch
                 {"level": "blocking", "text": "no place given"},
                 finding("major", "src/auth/login.py", 11, "kept")]
        passed, findings, text = review.review(
            2, TICKET, DIFF, lambda lens, inputs: {"verdict": "fail", "findings": found})
        self.assertTrue(passed, "every blocking finding pointed outside the change")
        self.assertEqual([f["text"] for f in findings], ["kept"])
        self.assertIn("dropped 3 finding(s) that point outside the change", text)

    def test_a_fail_verdict_with_no_blocking_finding_still_fails(self):
        passed, _, _ = review.review(4, TICKET, "d", lambda lens, i: {"verdict": "fail"})
        self.assertFalse(passed)

    def test_tier_3_passes_when_no_finding_blocks(self):
        passed, _, text = review.review(
            3, TICKET, DIFF,
            lambda lens, inputs: {"verdict": "pass",
                                  "findings": [finding("minor", "src/auth/login.py", 10)]})
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
