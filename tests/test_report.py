"""Tests for the done and still-to-do summary."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from driver import report
from driver.log import Log
from gate import plan as pl

PLAN = """---
id: shop
tickets: shop-1, shop-2, shop-3, shop-4, shop-5
---
## Task
Sell things.

## Design
A cart.

## Files
create cart.py

## Seams
cart.add

## Reuse
none

## Risks
- An empty cart.

## Assumptions
none

## Tickets
- shop-1: add. - shop-2: remove. - shop-3: total. - shop-4: pay. - shop-5: ship.
"""


class StateCase(unittest.TestCase):
    """A project folder and its own state folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = os.path.join(self.tmp.name, "project")
        os.mkdir(self.p)
        patch = mock.patch.dict(os.environ, {"TOLLGATE_STATE": os.path.join(self.tmp.name, "state")})
        patch.start()
        self.addCleanup(patch.stop)
        self.logs = report.logs_dir(self.p)


class ProgressTest(StateCase):
    def setUp(self):
        super().setUp()
        Path(self.p, pl.plan_path("shop")).parent.mkdir(parents=True)
        Path(self.p, pl.plan_path("shop")).write_text(PLAN)
        with Log(str(self.logs / "task-shop.jsonl"), task="shop") as log:
            log.add("plan_locked", path="plans/shop.json")
        self.ticket("shop-1", [("merged", {"commit": "c" * 40})], ready=True, tier=1)
        self.ticket("shop-2", [("waiting_for_merge", {"commit": "d" * 40})], ready=True, tier=4)
        self.ticket("shop-3", [("stopped", {"reason": "the same checks failed"}),
                               ("waiting_for_advisor", {"question": 12,
                                                        "reason": "the same checks failed"})])
        self.ticket("shop-4", [("try_started", {"attempt": 2})])

    def ticket(self, tid, events, ready=False, tier=None):
        with Log(str(self.logs / f"{tid}.jsonl"), ticket=tid, task="shop") as log:
            log.add("try_passed" if ready else "try_failed", attempt=1, score=100, tier=tier or 1)
            if ready:
                log.add("ready", branch=f"tg/{tid}", commit="c" * 40)
            for name, fields in events:
                log.add(name, **fields)

    def test_each_state_reads_as_one_sentence(self):
        done, todo = report.progress(self.p, "shop")
        self.assertEqual(done, ["Plan for shop: approved and locked.", "shop-1: merged."])
        self.assertEqual(todo, [
            "shop-2: built, branch tg/shop-2 waits to merge. It needs your approval: tier 4.",
            "shop-3: waits for your decision in question 12. The same checks failed.",
            "shop-4: being built, try 2.",
            "shop-5: not started."])

    def test_brief_has_two_short_lists(self):
        text = report.brief(self.p)
        self.assertTrue(text.startswith("Done\n- Plan for shop"))
        self.assertIn("\nStill to do\n- shop-2", text)
        self.assertNotIn("|", text)

    def test_a_task_waiting_for_plan_approval(self):
        with Log(str(self.logs / "task-blog.jsonl"), task="blog") as log:
            log.add("waiting_for_advisor", question=3, reason="review clean")
        _, todo = report.progress(self.p, "blog")
        self.assertEqual(todo, ["Plan for blog: waits for your approval in question 3."])

    def test_the_report_says_the_task_waits_only_while_it_does(self):
        path = str(self.logs / "task-blog.jsonl")
        with Log(path, task="blog") as log:
            log.add("started")
            log.add("waiting_for_advisor", by="person", question=1, reason="review clean")
            log.add("task_waiting", reason="asked in question 1")
            log.add("started")
            log.add("still_waiting", question=1)
            log.add("task_waiting", reason="question 1 waits for a decision")
        self.assertIn("The task waits: question 1 waits for a decision",
                      report.render(self.p, "blog"))
        with Log(path, task="blog") as log:
            log.add("started")
            log.add("advisor_decided", by="person", question=1, decision="approve", hint="")
            log.add("plan_locked", path="plans/blog.json")
        self.assertNotIn("The task waits", report.render(self.p, "blog"))

    def test_nothing_run_yet(self):
        with tempfile.TemporaryDirectory() as empty:
            empty = os.path.join(empty, "other")
            self.assertIn("- Nothing yet.", report.brief(empty))
            self.assertIn("- Nothing. Everything is done.", report.brief(empty))

    def test_the_task_report_starts_with_the_brief(self):
        text = Path(report.write(self.p, "shop")).read_text()
        self.assertTrue(text.startswith("# Report: task shop\n\nDone\n"))
        self.assertIn("## Details", text)

    def test_the_task_report_has_a_picture(self):
        import xml.etree.ElementTree as ET
        report.write(self.p, "shop")
        folder = Path(report.write(self.p, "shop")).parent
        self.assertFalse(Path(self.p, ".tollgate", "reports").exists())
        text = (folder / "shop.md").read_text()
        self.assertIn('srcset="shop-dark.svg"', text)
        for name in ("shop.svg", "shop-dark.svg"):
            root = ET.fromstring((folder / name).read_text())
            self.assertEqual(root.get("role"), "img")
            words = " ".join(e.text or "" for e in root.iter())
            self.assertIn("PLAN · LOCKED", words)
            self.assertIn("MERGED", words)



class RoadmapReportTest(StateCase):
    def log(self, rid, events):
        Path(self.logs, f"roadmap-{rid}.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in events))

    def roadmap(self, rid, tasks):
        Path(self.p, ".tollgate/roadmaps").mkdir(parents=True, exist_ok=True)
        lines = "".join(f"- {t}: do {t}.\n" for t in tasks[1:])
        Path(self.p, f".tollgate/roadmaps/{rid}.md").write_text(
            f"---\nid: {rid}\nchecklist: {rid}-done\n---\n## Request\nAll of it.\n\n"
            f"## Base\n- {tasks[0]}: the base.\n\n## Skeleton\n\n## Features\n{lines}\n"
            f"## Not yet specified\nMore.\n")

    def test_a_running_roadmap_shows_its_count_and_the_next_task(self):
        self.roadmap("orders", ["orders-base", "orders-create", "orders-list"])
        self.log("orders", [{"event": "checklist_frozen"},
                            {"event": "task_done", "stage": "Base", "task": "orders-base", "code": 0},
                            {"event": "base_passed"}])
        text = report.brief(self.p)
        self.assertIn("Roadmap orders: the base passes all five checks.", text)
        self.assertIn("Roadmap orders: 1 of 3 tasks done. Now: orders-create (features).", text)

    def test_a_stopped_roadmap_says_why_and_a_finished_one_says_done(self):
        self.log("a", [{"event": "checklist_frozen"},
                       {"event": "roadmap_waiting", "reason": "the base is not ready: one_log_line"}])
        self.log("b", [{"event": "task_done", "stage": "Base", "task": "b-1", "code": 0},
                       {"event": "roadmap_done"}])
        text = report.brief(self.p)
        self.assertIn("Roadmap a: stopped, 0 tasks done so far. The base is not ready", text)
        self.assertIn("Roadmap b: done. Its task and the checklist for the whole request pass.",
                      text)


class UnknownCostTest(unittest.TestCase):
    def test_a_cost_that_is_not_known_shows_as_unknown(self):
        known = [{"event": "started", "ticket": "T-1"}, {"event": "tests_written", "cost_usd": 0.5}]
        self.assertEqual(report.ticket_row(known)["cost_usd"], 0.5)
        session = [{"event": "started", "ticket": "T-1"}, {"event": "tests_written",
                                                           "cost_usd": None}]
        self.assertIsNone(report.ticket_row(session)["cost_usd"])
        self.assertEqual(report.usd(None), "unknown")
        self.assertEqual(report.usd(0.5), "0.5")


if __name__ == "__main__":
    unittest.main()
