import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from driver import retro

HEADER = ["| Number | Value |", "| --- | --- |"]


def run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = retro.main(argv)
    return code, out.getvalue()


class RetroPrintFlag(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = self.tmp.name
        self.lessons = Path(self.project, ".tollgate", "lessons", "X.md")

    def args(self, *extra):
        return ["--project", self.project, "--task", "X", *extra]

    def test_c1_numbers_table_markdown(self):
        table = retro.numbers_table({"mean_attempts": 1.5, "tests_rejected": 2})
        self.assertIsInstance(table, str)
        self.assertEqual(table.strip().splitlines(), HEADER + [
            "| mean attempts | 1.5 |", "| tests rejected | 2 |"])

    def test_c2_print_shows_table_and_writes_file(self):
        code, out = run(self.args("--print"))
        self.assertEqual(code, 0)
        self.assertIn("\n".join(HEADER), out)
        self.assertIn("| tickets | 0 |", out)
        self.assertTrue(self.lessons.exists())

    def test_c3_without_print_only_path(self):
        code, out = run(self.args())
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), str(self.lessons))
        nums, _ = retro.numbers(self.project, "X")
        expected = "\n".join(
            ["# Retro: task X", "", "| Number | Value |", "| --- | --- |"]
            + [f"| {k.replace('_', ' ')} | {v} |" for k, v in nums.items()]
            + ["", f"## Candidates for lessons (at most {retro.MAX_LESSONS})", "",
               "- None. No ticket stopped, had a test rejected, or needed a second attempt."]
        ) + "\n"
        self.assertEqual(self.lessons.read_text(), expected)

    def test_c4_printed_table_matches_file(self):
        _, out = run(self.args("--print"))
        table = retro.numbers_table(retro.numbers(self.project, "X")[0]).strip()
        self.assertIn(table, out)
        self.assertIn(table, self.lessons.read_text())

    def test_c5_print_in_help(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            retro.main(["--help"])
        self.assertIn("--print", out.getvalue())


if __name__ == "__main__":
    unittest.main()
