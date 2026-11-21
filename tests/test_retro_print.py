"""Tests for `retro --print`: the numbers table on standard output."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from driver import retro

HEAD = ["| Number | Value |", "| --- | --- |"]


class RetroPrintTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.p = tmp.name
        events = [
            {"event": "attempt_failed", "at": "2026-01-01T10:02:00Z", "ticket": "t-a",
             "task": "demo", "attempt": 1, "score": 50, "tier": 1},
            {"event": "attempt_passed", "at": "2026-01-01T10:03:00Z", "ticket": "t-a",
             "task": "demo", "attempt": 2, "score": 100, "tier": 1},
        ]
        path = Path(self.p, ".tollgate/logs/t-a.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in events))
        self.file = Path(self.p, ".tollgate/lessons/demo.md")

    def run_main(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            retro.main(["--project", self.p, "--task", "demo", *extra])
        return buf.getvalue()

    def table(self):
        return retro.numbers_table(retro.numbers(self.p, "demo")[0])

    def test_c1_numbers_table_lines(self):
        self.assertEqual(
            retro.numbers_table({"mean_attempts": 2, "tests_rejected": 0}),
            HEAD + ["| mean attempts | 2 |", "| tests rejected | 0 |"])

    def test_c2_print_shows_table_and_writes_file(self):
        out = self.run_main("--print")
        lines = out.strip().splitlines()
        table = self.table()
        self.assertTrue(self.file.exists())
        self.assertEqual(lines[-1], str(self.file))
        for line in table:
            self.assertIn(line, lines)
        self.assertLess(lines.index(table[0]), len(lines) - 1)
        self.assertLess(lines.index(table[-1]), len(lines) - 1)

    def test_c3_without_print_only_path(self):
        out = self.run_main()
        self.assertEqual(out.strip(), str(self.file))
        self.assertNotIn("| Number", out)
        nums = retro.numbers(self.p, "demo")[0]
        rows = [f"| {k.replace('_', ' ')} | {v} |" for k, v in nums.items()]
        expected = (["# Retro: task demo", ""] + HEAD + rows + [
            "", "## Candidates for lessons (at most 3)", ""] + [
            "- t-a: a test. Evidence: 0 rejected tests, 2 attempts"])
        self.assertEqual(self.file.read_text(), "\n".join(expected) + "\n")

    def test_c4_file_holds_printed_table(self):
        out = self.run_main("--print")
        text = self.file.read_text()
        printed = [ln for ln in out.splitlines() if ln.startswith("|")]
        self.assertTrue(printed)
        for line in printed:
            self.assertIn(line, text.splitlines())

    def test_c5_candidates_not_printed(self):
        out = self.run_main("--print")
        self.assertNotIn("## Candidates for lessons", out)
        self.assertNotIn("- None.", out)
        self.assertNotIn("- t-a:", out)
        text = self.file.read_text()
        self.assertIn("## Candidates for lessons", text)
        self.assertIn("- t-a: a ", text)


if __name__ == "__main__":
    unittest.main()
