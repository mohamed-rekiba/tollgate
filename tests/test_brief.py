"""The brief: .tollgate/briefs/<id>.md, what a brainstorm turns a rough idea into."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from gate import brief

BRIEF = """---
id: shout
size: task
---
## Overview
Shout turns a name into a loud greeting. It helps a user who wants a loud hello.

## Analysis
- need: greet already builds the greeting, so shout can reuse it [app.py::greet].
- risk: an empty name gives a greeting with no name.

## Goals
- shout("ann") returns "HELLO ANN".

## Non-goals
- Other languages.

## Alternatives weighed
- A loud flag on greet: dropped because it changes a function that other code calls.

## Open questions
- Should shout keep accents?
"""


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = brief.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FormatTest(unittest.TestCase):
    def test_a_brief_gives_its_goals_non_goals_alternatives_and_open_questions(self):
        found = brief.parse(BRIEF)
        self.assertEqual((found.id, found.size), ("shout", "task"))
        self.assertEqual(found.goals, ['shout("ann") returns "HELLO ANN".'])
        self.assertEqual(found.non_goals, ["Other languages."])
        self.assertEqual(found.alternatives, [
            ("A loud flag on greet", "it changes a function that other code calls.")])
        self.assertEqual(found.open_questions, ["Should shout keep accents?"])
        self.assertTrue(brief.is_brief(BRIEF))
        self.assertFalse(brief.is_brief("Add shout and whisper.\n"))

    def test_open_questions_may_be_none(self):
        text = BRIEF.replace("- Should shout keep accents?", "none")
        self.assertEqual(brief.parse(text).open_questions, [])

    def test_a_brief_too_big_for_one_task_says_roadmap(self):
        self.assertEqual(brief.parse(BRIEF.replace("size: task", "size: roadmap")).size,
                         "roadmap")

    def test_each_format_error_says_what_to_fix(self):
        cases = {
            "a brief starts with a --- line": BRIEF.replace("---\nid", "id", 1),
            "size: task or size: roadmap": BRIEF.replace("size: task", "size: huge"),
            "valid id": BRIEF.replace("id: shout", "id: no spaces here"),
            "empty or missing sections: Non-goals": BRIEF.replace("- Other languages.\n", ""),
            "must end with a question mark": BRIEF.replace("keep accents?", "keep accents."),
            "dropped because": BRIEF.replace(": dropped because", ", which"),
            "says the same thing twice": BRIEF.replace(
                "- risk: an empty", "- need: greet already builds the greeting, so shout can "
                "reuse it [app.py::greet].\n- risk: an empty"),
            "starts with - ": BRIEF.replace("- Other languages.", "Other languages."),
            "unknown header line": BRIEF.replace("size: task", "size: task\nowner: ann"),
        }
        for words, text in cases.items():
            with self.subTest(words), self.assertRaises(brief.BriefError) as err:
                brief.parse(text)
            self.assertIn(words, str(err.exception))


class CommandTest(unittest.TestCase):
    def project(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / ".tollgate/briefs").mkdir(parents=True)
        return root

    def test_a_brief_is_checked_and_copied_as_the_request_of_a_task(self):
        root = self.project()
        (root / ".tollgate/briefs/shout.md").write_text(BRIEF)
        to = root / ".tollgate/requests/shout.md"
        code, out, _ = cli("--project", str(root), "shout", "--to", str(to))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"id": "shout", "size": "task", "open_questions": 1})
        self.assertEqual(to.read_text(), BRIEF)

    def test_a_missing_brief_id_names_the_file_and_the_skill(self):
        root = self.project()
        code, out, err = cli("--project", str(root), "nope")
        self.assertEqual((code, out), (1, ""))
        self.assertIn(".tollgate/briefs/nope.md", err)
        self.assertIn("/tollgate:brainstorm", err)

    def test_a_brief_in_a_bad_format_is_refused_and_not_copied(self):
        root = self.project()
        (root / ".tollgate/briefs/shout.md").write_text(BRIEF.replace("## Goals", "## Aims"))
        to = root / ".tollgate/requests/shout.md"
        code, _, err = cli("--project", str(root), "shout", "--to", str(to))
        self.assertEqual(code, 1)
        self.assertIn("Goals", err)
        self.assertFalse(to.exists())

    def test_a_brief_id_that_is_not_a_plain_name_is_refused(self):
        root = self.project()
        code, _, err = cli("--project", str(root), "../settings")
        self.assertEqual(code, 1)
        self.assertIn("not a valid brief id", err)


if __name__ == "__main__":
    unittest.main()
