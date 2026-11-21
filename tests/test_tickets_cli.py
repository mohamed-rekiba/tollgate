"""Tests for the ticket file command line."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from action import tickets

ROOT = Path(__file__).resolve().parent.parent

VALID = """---
id: demo-1
plan: p-01
seams: a.b
tests: tests/test_demo.py
---
## Current behavior
Nothing.

## Desired behavior
Something.

## Checklist
- [C1, must] first thing works
- [C2, must, keeps behavior] old thing stays
- [C3] third thing

## Out of scope
Else.
"""

BROKEN = VALID.replace("## Out of scope\nElse.\n", "")


def run_main(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = tickets.main(args)
    return code, out.getvalue(), err.getvalue()


class TicketCliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_c1_valid_ticket_prints_id_and_items(self):
        code, out, err = run_main([self.write("t.md", VALID)])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        lines = out.splitlines()
        self.assertEqual(lines[0], "id: demo-1")
        self.assertEqual(len(lines), 4)
        for line, (cid, text) in zip(
            lines[1:],
            [("C1", "first thing works"), ("C2", "old thing stays"), ("C3", "third thing")],
        ):
            self.assertIn(cid, line)
            self.assertIn(text, line)
        self.assertIn("must", lines[1])
        self.assertIn("keeps behavior", lines[2])

    def test_c2_broken_ticket_errors_on_stderr_only(self):
        with self.assertRaises(tickets.TicketError) as ctx:
            tickets.parse(BROKEN)
        code, out, err = run_main([self.write("t.md", BROKEN)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error:"))
        self.assertIn(str(ctx.exception), err)

    def test_c3_missing_and_non_utf8_file(self):
        code, out, err = run_main([str(self.dir / "nope.md")])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error:"))
        self.assertNotIn("Traceback", err)
        bad = self.dir / "bad.md"
        bad.write_bytes(b"---\nid: \xff\xfe\n---\n")
        code, out, err = run_main([str(bad)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("error:"))
        self.assertNotIn("Traceback", err)

    def test_c4_wrong_number_of_arguments(self):
        path = self.write("t.md", VALID)
        for args in ([], [path, path]):
            code, out, err = run_main(args)
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertTrue(err.startswith("error:"))

    def test_c5_parse_unchanged_and_import_silent(self):
        ticket = tickets.parse(VALID)
        self.assertEqual(ticket.id, "demo-1")
        self.assertEqual(ticket.tests, ["tests/test_demo.py"])
        self.assertEqual([i.id for i in ticket.items], ["C1", "C2", "C3"])
        self.assertTrue(ticket.item("C2").keeps_behavior)
        self.assertEqual(tickets.item_of_test("test_c2_fails"), "C2")
        with self.assertRaises(tickets.TicketError):
            tickets.parse("no header")
        proc = subprocess.run(
            [sys.executable, "-c", "import action.tickets"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")
        self.assertEqual(proc.stderr, "")

    def test_c6_process_matches_main(self):
        for text in (VALID, BROKEN):
            path = self.write("t.md", text)
            code, out, err = run_main([path])
            proc = subprocess.run(
                [sys.executable, "-m", "action.tickets", path],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, code)
            self.assertEqual(proc.stdout, out)
            self.assertEqual(proc.stderr, err)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
