"""Tests for the action.plan command line."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from action import plan

GOOD = """---
id: retries
tickets: T-1, T-2
---
## Task
ask
## Design
design
## Files
a.py
## Seams
s
## Tickets
T-1: one.
T-2: two.
"""


def run(text=None, path=None):
    with tempfile.TemporaryDirectory() as d:
        if path is None:
            path = Path(d) / "plan.md"
            path.write_text(text)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = plan.main([str(path)])
    return code, out.getvalue(), err.getvalue()


class PlanCliTest(unittest.TestCase):
    def test_good_plan_prints_id_and_tickets(self):
        code, out, _ = run(GOOD)
        self.assertEqual(code, 0)
        self.assertIn("id: retries", out)
        self.assertIn("tickets: T-1, T-2", out)

    def test_bad_plan_prints_error(self):
        code, out, err = run(GOOD.replace("T-2: two.", ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("T-2", err)

    def test_missing_file(self):
        code, _, err = run(path="/nonexistent/plan.md")
        self.assertEqual(code, 1)
        self.assertIn("error", err)


if __name__ == "__main__":
    unittest.main()
