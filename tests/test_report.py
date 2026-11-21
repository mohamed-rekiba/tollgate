"""Tests for the done and still-to-do summary."""

import tempfile
import unittest
from pathlib import Path

from action import plan as pl
from driver import report
from driver.log import Log

PLAN = """---
id: shop
tickets: shop-1, shop-2, shop-3, shop-4, shop-5
---
## Task
Sell things.

## Design
A cart.

## Files
cart.py

## Seams
cart.add

## Tickets
- shop-1: add. - shop-2: remove. - shop-3: total. - shop-4: pay. - shop-5: ship.
"""


class ProgressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = self.tmp.name
        Path(self.p, pl.plan_path("shop")).parent.mkdir(parents=True)
        Path(self.p, pl.plan_path("shop")).write_text(PLAN)
        logs = Path(self.p, ".tollgate/logs")
        with Log(str(logs / "task-shop.jsonl"), task="shop") as log:
            log.add("plan_locked", tag="tg/plan/shop/1")
        self.ticket("shop-1", [("merged", {"pr": 7})], pr=7, tier=1)
        self.ticket("shop-2", [("waiting_for_merge", {"pr": 8})], pr=8, tier=4)
        self.ticket("shop-3", [("stopped", {"reason": "the same checks failed"}),
                               ("waiting_for_advisor", {"issue": 12, "reason": "the same checks failed"})])
        self.ticket("shop-4", [("attempt_started", {"attempt": 2})])

    def ticket(self, tid, events, pr=None, tier=None):
        with Log(str(Path(self.p, ".tollgate/logs", f"{tid}.jsonl")), ticket=tid, task="shop") as log:
            log.add("attempt_passed" if pr else "attempt_failed", attempt=1, score=100, tier=tier or 1)
            if pr:
                log.add("pr_opened", pr=pr, commit="c")
            for name, fields in events:
                log.add(name, **fields)

    def test_each_state_reads_as_one_sentence(self):
        done, todo = report.progress(self.p, "shop")
        self.assertEqual(done, ["Plan for shop: approved and locked.",
                                "shop-1: merged (pull request #7)."])
        self.assertEqual(todo, [
            "shop-2: built, pull request #8 waits to merge. It needs your approval: tier 4.",
            "shop-3: waits for your decision in issue #12. The same checks failed.",
            "shop-4: being built, attempt 2.",
            "shop-5: not started."])

    def test_brief_has_two_short_lists(self):
        text = report.brief(self.p)
        self.assertTrue(text.startswith("Done\n- Plan for shop"))
        self.assertIn("\nStill to do\n- shop-2", text)
        self.assertNotIn("|", text)

    def test_a_task_waiting_for_plan_approval(self):
        with Log(str(Path(self.p, ".tollgate/logs/task-blog.jsonl")), task="blog") as log:
            log.add("waiting_for_advisor", issue=3, reason="review clean")
        _, todo = report.progress(self.p, "blog")
        self.assertEqual(todo, ["Plan for blog: waits for your approval in issue #3."])

    def test_nothing_run_yet(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIn("- Nothing yet.", report.brief(empty))
            self.assertIn("- Nothing. Everything is done.", report.brief(empty))

    def test_the_task_report_starts_with_the_brief(self):
        text = Path(report.write(self.p, "shop")).read_text()
        self.assertTrue(text.startswith("# Report: task shop\n\nDone\n"))
        self.assertIn("## Details", text)

    def test_the_task_report_has_a_picture(self):
        import xml.etree.ElementTree as ET
        report.write(self.p, "shop")
        folder = Path(self.p, ".tollgate", "reports")
        text = (folder / "shop.md").read_text()
        self.assertIn('srcset="shop-dark.svg"', text)
        for name in ("shop.svg", "shop-dark.svg"):
            root = ET.fromstring((folder / name).read_text())
            self.assertEqual(root.get("role"), "img")
            words = " ".join(e.text or "" for e in root.iter())
            self.assertIn("PLAN · LOCKED", words)
            self.assertIn("MERGED", words)


if __name__ == "__main__":
    unittest.main()
