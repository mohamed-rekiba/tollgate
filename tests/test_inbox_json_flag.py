import contextlib
import io
import json
import unittest

from setup import inbox
from setup.gh import GhError


class StubGh:
    def __init__(self, issues=None, broken=()):
        self.issues = issues or {}
        self.broken = broken

    def get(self, path):
        repo = path.split("/issues")[0].replace("repos/", "")
        if repo in self.broken:
            raise GhError(404, "not found")
        return self.issues.get(repo, [])


ISSUE = {"number": 7, "title": "Which color?", "html_url": "https://x/o/r/issues/7"}


def run(argv, gh):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = inbox.main(argv, gh)
    return code, buf.getvalue()


class InboxJsonFlag(unittest.TestCase):
    def test_c1_json_prints_one_list_with_keys(self):
        code, out = run(["--repo", "o/r", "--json"], StubGh({"o/r": [ISSUE]}))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data, [{"repo": "o/r", "issue": 7, "title": "Which color?",
                                 "url": "https://x/o/r/issues/7"}])

    def test_c2_json_with_no_questions_is_empty_list(self):
        _, out = run(["--repo", "o/r", "--json"], StubGh())
        self.assertEqual(json.loads(out), [])
        self.assertNotIn("Nothing waits", out)

    def test_c3_text_output_unchanged(self):
        _, out = run(["--repo", "o/r"], StubGh({"o/r": [ISSUE]}))
        self.assertEqual(out, "o/r#7\tWhich color?\thttps://x/o/r/issues/7\n")
        _, out = run(["--repo", "o/r"], StubGh())
        self.assertEqual(out, "Nothing waits for a person.\n")

    def test_c4_unreadable_repo_shows_with_null_issue(self):
        _, out = run(["--repo", "o/r", "--json"], StubGh(broken=("o/r",)))
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["repo"], "o/r")
        self.assertIsNone(data[0]["issue"])


if __name__ == "__main__":
    unittest.main()
