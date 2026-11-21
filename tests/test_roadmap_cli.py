"""Tests for python3 -m action.roadmap <path>."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from action import roadmap

GOOD = """---
id: orders
checklist: orders-done
---
## Request
Orders.
## Base
- orders-base: Build it.
## Skeleton
- orders-rules: Rules.
## Features
- orders-create: Create an order.
## Not yet specified
Everything else.
"""


class RoadmapCliTest(unittest.TestCase):
    def run_cli(self, text=None, name="r.md"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / name
        if text is not None:
            path.write_text(text)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = roadmap.main([str(path)])
        return code, out.getvalue(), err.getvalue()

    def test_valid_prints_tasks_in_build_order(self):
        code, out, _ = self.run_cli(GOOD)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Base\torders-base", "Skeleton\torders-rules",
                                            "Features\torders-create"])

    def test_invalid_prints_error_and_fails(self):
        code, out, err = self.run_cli("\n".join(l for l in GOOD.splitlines() if not l.startswith("- ")))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("error:", err)

    def test_not_a_roadmap(self):
        code, _, err = self.run_cli("hello\n")
        self.assertEqual(code, 1)
        self.assertIn("header", err)

    def test_missing_file(self):
        code, _, err = self.run_cli(None)
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)


if __name__ == "__main__":
    unittest.main()
