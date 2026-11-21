"""Tests for setup.inbox, including --json."""

import contextlib
import io
import json
import unittest

from setup import inbox
from setup.gh import GhError


class StubGh:
    def get(self, path):
        if "bad/repo" in path:
            raise GhError(500, "boom")
        if "o/empty" in path:
            return []
        return [{"number": 7, "title": "Which db?", "html_url": "http://x/7"}]


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = inbox.main(list(argv), StubGh())
    return code, buf.getvalue()


class InboxJson(unittest.TestCase):
    def test_json_is_one_list(self):
        code, out = run("--repo", "o/r", "--repo", "o/empty", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [
            {"repo": "o/r", "issue": 7, "title": "Which db?", "url": "http://x/7"}])

    def test_json_empty_is_empty_list(self):
        _, out = run("--repo", "o/empty", "--json")
        self.assertEqual(json.loads(out), [])

    def test_json_keeps_read_errors(self):
        _, out = run("--repo", "bad/repo", "--json")
        data = json.loads(out)
        self.assertIsNone(data[0]["issue"])
        self.assertIn("boom", data[0]["title"])

    def test_text_unchanged(self):
        _, out = run("--repo", "o/r")
        self.assertEqual(out, "o/r#7\tWhich db?\thttp://x/7\n")
        _, out = run("--repo", "o/empty")
        self.assertEqual(out, "Nothing waits for a person.\n")


if __name__ == "__main__":
    unittest.main()
