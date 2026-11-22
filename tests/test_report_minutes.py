"""Tests for the Minutes column of the status table and the task report."""

import json
import os
import tempfile
import unittest
from unittest import mock

from driver import report

OLD_REPORT_HEAD = ["Ticket", "State", "Tier", "Tries", "Score", "Cost USD", "Ready change", "Why"]
OLD_STATUS_HEAD = ["Task", "Ticket", "State", "Tier", "Tries", "Score", "Cost USD", "Ready change"]


def ev(event, at=None, **fields):
    e = {"event": event, **fields}
    if at:
        e["at"] = at
    return e


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


class MinutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = os.path.join(self.tmp.name, "project")
        os.mkdir(self.p)
        patch = mock.patch.dict(os.environ, {"TOLLGATE_STATE": os.path.join(self.tmp.name, "state")})
        patch.start()
        self.addCleanup(patch.stop)
        # t-a: 3 minutes (10:02 to 10:05). t-b: 100 seconds (10:08:20 to 10:10:00, rounds up to 2). Task spans 10 minutes.
        self.write("task-demo", [ev("plan_locked", "2026-01-01T10:00:00Z", task="demo")])
        self.write("t-a", [
            ev("try_failed", "2026-01-01T10:02:00Z", ticket="t-a", task="demo", attempt=1, score=50, tier=1),
            ev("try_passed", "2026-01-01T10:03:00Z", ticket="t-a", task="demo", attempt=2, score=100, tier=1),
            ev("ready", "2026-01-01T10:05:00Z", ticket="t-a", task="demo", commit="c" * 40),
        ])
        self.write("t-b", [
            ev("try_failed", "2026-01-01T10:08:20Z", ticket="t-b", task="demo", attempt=1, score=10, tier=2),
            ev("stopped", "2026-01-01T10:09:30Z", ticket="t-b", task="demo", reason="why not"),
            ev("task_marker", "2026-01-01T10:10:00Z", ticket="t-b", task="demo"),
        ])

    def write(self, name, events):
        path = report.logs_dir(self.p) / f"{name}.jsonl"
        path.write_text("".join(json.dumps(e) + "\n" for e in events))

    def table(self, text, first_cell):
        lines = [ln for ln in text.splitlines() if ln.startswith("|")]
        head = next(ln for ln in lines if cells(ln)[0] == first_cell)
        body = [ln for ln in lines if ln != head and not set(ln) <= set("| -")]
        sep = lines[lines.index(head) + 1]
        return cells(head), cells(sep), [cells(ln) for ln in body]

    def test_c1_ticket_row_minutes(self):
        ninety = [ev("started", "2026-01-01T10:00:00Z", ticket="x"),
                  ev("stopped", "2026-01-01T10:01:30Z", ticket="x")]
        self.assertEqual(report.ticket_row(ninety)["minutes"], 2)
        short = [ev("started", "2026-01-01T10:00:00Z", ticket="x"),
                 ev("stopped", "2026-01-01T10:00:29Z", ticket="x")]
        self.assertEqual(report.ticket_row(short)["minutes"], 0)
        three = [ev("started", "2026-01-01T10:00:00Z"), ev("frozen", "2026-01-01T10:01:00Z"),
                 ev("merged", "2026-01-01T10:03:00Z")]
        self.assertEqual(report.ticket_row(three)["minutes"], 3)

    def test_c2_status_has_minutes_column(self):
        head, sep, body = self.table(report.status(self.p), "Task")
        i = head.index("Cost USD")
        self.assertEqual(head[i + 1], "Minutes")
        self.assertEqual(len(sep), len(head))
        self.assertEqual(head[i + 2], "Ready change")
        by_ticket = {r[1]: r for r in body}
        self.assertEqual(by_ticket["t-a"][i + 1], "3")
        self.assertEqual(by_ticket["t-b"][i + 1], "2")

    def test_c3_render_has_minutes_column(self):
        head, sep, body = self.table(report.render(self.p, "demo"), "Ticket")
        i = head.index("Cost USD")
        self.assertEqual(head[i + 1], "Minutes")
        self.assertEqual(len(sep), len(head))
        by_ticket = {r[0]: r for r in body}
        self.assertEqual(by_ticket["t-a"][i + 1], "3")
        self.assertEqual(by_ticket["t-b"][i + 1], "2")

    def test_c4_single_event_or_no_stamps_shows_zero(self):
        self.assertEqual(report.ticket_row([ev("started", "2026-01-01T10:00:00Z", ticket="x")])["minutes"], 0)
        self.assertEqual(report.ticket_row([ev("started", ticket="x"), ev("stopped", ticket="x")])["minutes"], 0)

    def test_c5_other_columns_and_time_line_unchanged(self):
        text = report.render(self.p, "demo")
        self.assertIn("- Time: 10 minutes from the first event to the last.", text)
        head, _, body = self.table(text, "Ticket")
        i = head.index("Minutes") if "Minutes" in head else None
        drop = lambda row: [c for j, c in enumerate(row) if j != i]
        self.assertEqual(drop(head), OLD_REPORT_HEAD)
        by_ticket = {r[0]: drop(r) for r in body}
        self.assertEqual(by_ticket["t-a"][:4], ["t-a", "ready to merge", "1", "2"])
        self.assertEqual(by_ticket["t-a"][6], "tg/t-a at cccccccccccc")
        self.assertEqual(by_ticket["t-b"][7], "why not")
        shead, _, _ = self.table(report.status(self.p), "Task")
        j = shead.index("Minutes") if "Minutes" in shead else None
        self.assertEqual([c for k, c in enumerate(shead) if k != j], OLD_STATUS_HEAD)


if __name__ == "__main__":
    unittest.main()
