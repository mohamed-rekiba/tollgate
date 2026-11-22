"""Tests for the analysis format and the check of its citations."""

import tempfile
import unittest
from pathlib import Path

from gate import analysis as an
from tests.helpers import within

TEXT = """---
task: retries
commit: 3d549d7
---
## Structure
- confirmed: the sender lives in one module [src/send.py:1]
## Entry points
- confirmed: the web handler calls send [src/web.py::deliver]
## Frameworks
- assumed: the project runs on Python 3.11
## Similar features
- confirmed: timeouts are retried the same way [src/send.py:3]
## Tests
- confirmed: tests use unittest [tests/test_send.py:1]
## Standards
- assumed: no written standards beyond the README
"""


def project():
    d = tempfile.mkdtemp()
    Path(d, "src").mkdir()
    Path(d, "tests").mkdir()
    Path(d, "src/send.py").write_text("def send():\n    pass\n# retry on timeout\n")
    Path(d, "src/web.py").write_text("def deliver(req):\n    return send()\n")
    Path(d, "tests/test_send.py").write_text("import unittest\n")
    return d


class FormatTest(unittest.TestCase):
    def test_reads_the_six_sections(self):
        a = an.parse(TEXT)
        self.assertEqual((a.task, a.commit), ("retries", "3d549d7"))
        self.assertEqual(list(a.sections), list(an.SECTIONS))
        first = a.sections["Structure"][0]
        self.assertEqual((first.status, first.cites), ("confirmed", [("src/send.py", 1, None)]))
        self.assertEqual(a.sections["Entry points"][0].cites, [("src/web.py", None, "deliver")])

    def test_refuses_a_missing_section(self):
        with self.assertRaisesRegex(an.AnalysisError, "Tests"):
            an.parse(TEXT.replace("## Tests\n- confirmed: tests use unittest [tests/test_send.py:1]\n", ""))

    def test_refuses_a_header_with_no_commit(self):
        with self.assertRaisesRegex(an.AnalysisError, "commit"):
            an.parse(TEXT.replace("commit: 3d549d7\n", ""))

    def test_each_finding_is_confirmed_or_assumed(self):
        with self.assertRaisesRegex(an.AnalysisError, "confirmed or assumed: the sender"):
            an.parse(TEXT.replace("- confirmed: the sender", "- the sender"))

    def test_a_confirmed_finding_cites_the_code(self):
        with self.assertRaisesRegex(an.AnalysisError, "cites no code: tests use unittest"):
            an.parse(TEXT.replace(" [tests/test_send.py:1]", ""))

    def test_a_long_broken_citation_is_read_quickly(self):
        broken = "- confirmed: tests use unittest [" + "!/" * 40 + "\n"
        with within(2), self.assertRaisesRegex(an.AnalysisError, "cites no code"):
            an.parse(TEXT.replace("- confirmed: tests use unittest [tests/test_send.py:1]\n", broken))


class VerifyTest(unittest.TestCase):
    def test_every_citation_that_exists_stays_confirmed(self):
        a = an.parse(TEXT)
        self.assertEqual(an.verify(a, project()), [])
        self.assertTrue(all(f.status == "confirmed" for f in a.sections["Structure"]))

    def test_a_citation_that_does_not_exist_makes_the_finding_assumed(self):
        bad = (TEXT.replace("[src/send.py:1]", "[src/send.py:40]")
               .replace("[src/web.py::deliver]", "[src/web.py::receive]")
               .replace("[tests/test_send.py:1]", "[tests/test_gone.py:1]"))
        a = an.parse(bad)
        demoted = an.verify(a, project())
        self.assertEqual(demoted, ["src/send.py:40", "src/web.py::receive", "tests/test_gone.py:1"])
        self.assertEqual(a.sections["Structure"][0].status, "assumed")
        self.assertIn("not found: src/send.py:40", an.render(a))

    def test_a_citation_cannot_leave_the_project(self):
        a = an.parse(TEXT.replace("[src/send.py:1]", "[../../etc/passwd:1]"))
        self.assertEqual(an.verify(a, project()), ["../../etc/passwd:1"])

    def test_render_reads_back_the_same(self):
        a = an.parse(TEXT)
        self.assertEqual(an.render(an.parse(an.render(a))), an.render(a))



class SameRuleTest(unittest.TestCase):
    def test_the_copied_check_and_the_gate_find_a_name_the_same_way(self):
        from gate import paths
        from setup import check_writing
        self.assertEqual(paths.DEFINES, check_writing.DEFINES)


class CommandTest(unittest.TestCase):
    def run_main(self, text, root):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(text)), redirect_stdout(out):
            code = an.main(["--root", root])
        return code, out.getvalue()

    def test_prints_the_checked_analysis(self):
        code, out = self.run_main(TEXT.replace("[src/send.py:1]", "[src/send.py:40]"), project())
        self.assertEqual(code, 0)
        self.assertIn("- assumed: the sender lives in one module [src/send.py:40] "
                      "(not found: src/send.py:40)", out)
        self.assertIn("Not found, so made assumptions: src/send.py:40", out)

    def test_a_bad_analysis_ends_with_1_and_says_why(self):
        code, out = self.run_main("no header", project())
        self.assertEqual(code, 1)
        self.assertIn("an analysis starts with a --- line", out)

if __name__ == "__main__":
    unittest.main()
