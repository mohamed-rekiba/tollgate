"""Tests for the command line of action.tickets."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from action import tickets

GOOD = """---
id: T-1
tests: tests/test_a.py
---
## Current behavior
a
## Desired behavior
b
## Checklist
- [C1, must] first
- [C2, must, keeps behavior] second
- [C3] third
## Out of scope
none
"""


class TicketsCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def run_main(self, path):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = tickets.main([str(path)])
        return code, out.getvalue()

    def test_good_ticket_prints_id_and_items(self):
        p = self.dir / "t.md"
        p.write_text(GOOD)
        code, out = self.run_main(p)
        self.assertEqual(code, 0)
        self.assertIn("id: T-1", out)
        self.assertIn("- [C1, must] first", out)
        self.assertIn("- [C2, must, keeps behavior] second", out)
        self.assertIn("- [C3] third", out)

    def test_bad_ticket_prints_error(self):
        p = self.dir / "t.md"
        p.write_text("no header\n")
        code, out = self.run_main(p)
        self.assertEqual(code, 1)
        self.assertIn("error:", out)
        self.assertIn("header", out)

    def test_missing_file_ends_with_1(self):
        code, out = self.run_main(self.dir / "nope.md")
        self.assertEqual(code, 1)
        self.assertIn("error:", out)

    def test_module_runs_as_command(self):
        p = self.dir / "t.md"
        p.write_text(GOOD)
        r = subprocess.run([sys.executable, "-m", "action.tickets", str(p)], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(r.returncode, 0)
        self.assertIn("id: T-1", r.stdout)


if __name__ == "__main__":
    unittest.main()
