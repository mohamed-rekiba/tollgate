"""Tests for the writing check and its installer, on throwaway git repositories."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from setup import check_writing, install_writing_check

WORDS = """# Shop

**ticket**: One small part of a plan.
_Avoid_: issue, work item

**gate**: The check that decides whether a change may merge.
_Avoid_: judge, ticket

**workflow**: The steps a ticket goes through.
_Avoid_: Action, item
"""

README = """# Shop

Shop sells books online.

## Why
## Start
## When to use it
"""


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


class Repo:
    """A repository whose main branch holds a word list and a good README."""

    def __init__(self, root: Path):
        self.root = root
        sh(root, "git", "init", "-q", "-b", "main")
        sh(root, "git", "config", "user.email", "owner@example.com")
        sh(root, "git", "config", "user.name", "Owner")
        self.write("CONTEXT.md", WORDS)
        self.write("README.md", README)
        self.commit("docs: start")
        sh(root, "git", "update-ref", "refs/heads/main", "HEAD")
        sh(root, "git", "checkout", "-q", "-b", "change")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message):
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "--allow-empty", "-m", message)

    def check(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_writing.main(str(self.root), **kw)
        return code, out.getvalue()


class CheckWritingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_clean_change_passes(self):
        self.repo.write("docs/guide.md", "The gate checks each ticket.\n")
        self.repo.commit("docs(guide): say what the gate checks")
        self.assertEqual(self.repo.check(), (0, ""))

    def test_a_word_to_avoid_names_the_term_to_use(self):
        self.repo.write("docs/guide.md", "Open an issue for each judge.\n")
        self.repo.commit("docs(guide): add a guide")
        code, out = self.repo.check()
        self.assertEqual(code, 1)
        self.assertIn("docs/guide.md:1: 'issue'. The word list says: ticket.", out)
        self.assertIn("docs/guide.md:1: 'judge'. The word list says: gate.", out)

    def test_filler_names_the_plain_word_or_says_to_cut(self):
        self.repo.write("docs/guide.md", "We leverage the gate.\nIt's worth noting the ticket.\n")
        self.repo.commit("docs(guide): add a guide")
        code, out = self.repo.check()
        self.assertEqual(code, 1)
        self.assertIn("docs/guide.md:1: 'leverage' is filler. Say 'use'.", out)
        self.assertIn("docs/guide.md:2: 'it's worth noting' is filler. Cut the sentence.", out)

    def test_a_capitalized_word_is_a_name_and_a_term_is_never_avoided(self):
        self.repo.write("docs/guide.md", "Lead with the action. The ticket is small.\n"
                        "The Action runs it.\n")
        self.repo.commit("docs(guide): add a guide")
        out = self.repo.check()[1]
        self.assertEqual(out, "docs/guide.md:2: 'Action'. The word list says: workflow.\n")

    def test_a_longer_word_wins_over_a_word_inside_it(self):
        self.repo.write("docs/guide.md", "Each work item.\n")
        self.repo.commit("docs(guide): add a guide")
        self.assertEqual(self.repo.check()[1],
                         "docs/guide.md:1: 'work item'. The word list says: ticket.\n")

    def test_code_quotes_and_links_are_not_checked(self):
        self.repo.write("docs/guide.md", 'Run `issue` here. The word "judge" is old. '
                        "[Read](https://example.com/issue).\n\n```\nissue\n```\n")
        self.repo.commit("docs(guide): add a guide")
        self.assertEqual(self.repo.check(), (0, ""))

    def test_only_added_lines_are_checked(self):
        self.repo.write("docs/old.md", "An issue from before.\n")
        self.repo.commit("docs: an old page")
        sh(self.repo.root, "git", "update-ref", "refs/heads/main", "HEAD")
        self.repo.write("docs/old.md", "An issue from before.\nA new line.\n")
        self.repo.commit("docs(old): add a line")
        self.assertEqual(self.repo.check(), (0, ""))

    def test_a_long_dash_fails(self):
        self.repo.write("docs/guide.md", "The gate — a check.\n")
        self.repo.commit("docs(guide): add a guide")
        self.assertIn("a long dash", self.repo.check()[1])

    def test_a_readme_must_answer_its_four_questions(self):
        self.repo.write("README.md", "# Shop\n\n## Install\n")
        self.repo.commit("docs(readme): shorten")
        out = self.repo.check()[1]
        self.assertIn("no opening sentence", out)
        self.assertIn("does not answer why it exists", out)
        self.assertIn("does not answer when to use it", out)
        self.assertNotIn("how to start", out)

    def test_a_commit_subject_needs_the_form(self):
        self.repo.commit("Fixed stuff")
        out = self.repo.check()[1]
        self.assertIn("subject 'Fixed stuff' is not 'type(scope): subject'", out)

    def test_a_commit_that_credits_an_ai_fails(self):
        self.repo.commit("fix(shop): a fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        self.assertIn("credits an AI", self.repo.check()[1])

    def test_with_no_main_to_compare_only_the_readme_is_checked(self):
        self.repo.commit("Fixed stuff")
        code, out = self.repo.check(base="no-such-branch")
        self.assertEqual(code, 0)
        self.assertIn("only the README is checked", out)

    def test_a_plain_comment_in_source_passes(self):
        self.repo.write("src/a.py", '"""Count the books."""\n\nleverage = 1  # the plain count\n')
        self.repo.write("src/b.ts", "// Count the books.\nconst s = \"a — b\";\n")
        self.repo.commit("feat(shop): count")
        self.assertEqual(self.repo.check(), (0, ""))

    def test_filler_or_a_long_dash_in_a_comment_fails_but_not_the_word_list(self):
        self.repo.write("src/a.py", 'def f():\n    """We leverage the issue."""\n'
                        "    return 1  # one — two\n")
        self.repo.write("src/b.go", "package b\n/* we utilize\n   this */\nvar x = 1 // a — b\n")
        self.repo.commit("feat(shop): count")
        out = self.repo.check()[1]
        self.assertIn("src/a.py:2: 'leverage' is filler", out)
        self.assertIn("src/a.py:3: a long dash", out)
        self.assertIn("src/b.go:2: 'utilize' is filler", out)
        self.assertIn("src/b.go:4: a long dash", out)
        self.assertNotIn("'issue'", out)

    def test_staged_checks_the_staged_change(self):
        self.repo.write("docs/guide.md", "The gate checks each ticket.\n")
        sh(self.repo.root, "git", "add", "-A")
        self.assertEqual(self.repo.check(staged=True), (0, ""))
        self.repo.write("docs/guide.md", "We leverage the gate.\n")
        sh(self.repo.root, "git", "add", "-A")
        self.assertEqual(self.repo.check(staged=True)[0], 1)

    def test_the_driver_commit_subjects_pass(self):
        for subject in ("test(shop-1): the ticket and its locked tests",
                        "feat(shop-1): attempt 2", "docs(order-totals): the plan"):
            self.assertTrue(check_writing.SUBJECT.match(subject), subject)


class InstallTest(unittest.TestCase):
    def test_install_copies_the_check_and_adds_it_as_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".tollgate").mkdir()
            Path(tmp, ".tollgate/settings.json").write_text(json.dumps(
                {"checks": {"tests": {"run": "pytest"}}, "harness": ["tests/helpers.py"]}))
            changed = install_writing_check.install(tmp)
            self.assertEqual(changed, [install_writing_check.TARGET, install_writing_check.SETTINGS])
            settings = json.loads(Path(tmp, ".tollgate/settings.json").read_text())
            self.assertEqual(settings["checks"]["writing"],
                             {"run": "python3 .tollgate/checks/check_writing.py"})
            self.assertIn("tests", settings["checks"])
            self.assertEqual(settings["harness"],
                             ["tests/helpers.py", ".tollgate/checks/check_writing.py"])
            self.assertEqual(Path(tmp, install_writing_check.TARGET).read_bytes(),
                             install_writing_check.SOURCE.read_bytes())
            self.assertEqual(install_writing_check.install(tmp), [])

    def test_help_installs_nothing_and_project_names_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                install_writing_check.main(["--help", "--project", tmp])
            self.assertFalse(Path(tmp, install_writing_check.TARGET).exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(install_writing_check.main(["--project", tmp]), 0)
            self.assertTrue(Path(tmp, install_writing_check.TARGET).exists())

    def test_the_copy_runs_alone_with_no_tollgate_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(Path(tmp))
            install_writing_check.install(tmp)
            repo.commit("chore(writing): install the check")
            proc = subprocess.run(["python3", "-I", ".tollgate/checks/check_writing.py"],
                                  cwd=tmp, capture_output=True, text=True, check=False)
            self.assertEqual((proc.returncode, proc.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
