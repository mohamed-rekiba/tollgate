"""Tests for inbox --json."""

import contextlib
import io
import json
import unittest

from setup import inbox
from setup.gh import GhError


class FakeGh:
    def __init__(self, issues=None, bad=()):
        self.issues = issues or {}
        self.bad = set(bad)

    def get(self, path):
        repo = "/".join(path.split("/")[1:3])
        if repo in self.bad:
            raise GhError(404, "Not Found")
        return self.issues.get(repo, [])


def issue(n, title):
    return {"number": n, "title": title, "html_url": f"https://github.com/x/y/issues/{n}"}


def run(argv, gh):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = inbox.main(argv, gh)
    return code, buf.getvalue()


class InboxJsonTest(unittest.TestCase):
    def test_c1_json_list_with_keys(self):
        gh = FakeGh({"o/r": [issue(1, "First?"), issue(2, "Second?")]})
        code, out = run(["--repo", "o/r", "--json"], gh)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 2)
        for item, n, t in zip(data, (1, 2), ("First?", "Second?")):
            self.assertEqual(item["repo"], "o/r")
            self.assertEqual(item["issue"], n)
            self.assertEqual(item["title"], t)
            self.assertEqual(item["url"], f"https://github.com/x/y/issues/{n}")

    def test_c2_json_empty_list(self):
        code, out = run(["--repo", "o/r", "--json"], FakeGh())
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])
        self.assertNotIn("Nothing", out)

    def test_c3_text_output_unchanged(self):
        gh = FakeGh({"o/r": [issue(7, "Which one?")]})
        code, out = run(["--repo", "o/r"], gh)
        self.assertEqual(code, 0)
        self.assertEqual(out, "o/r#7\tWhich one?\thttps://github.com/x/y/issues/7\n")
        code, out = run(["--repo", "o/empty"], FakeGh())
        self.assertEqual(code, 0)
        self.assertEqual(out, "Nothing waits for a person.\n")

    def test_c4_unreadable_repo_item(self):
        code, out = run(["--repo", "o/bad", "--json"], FakeGh(bad=["o/bad"]))
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["repo"], "o/bad")
        self.assertIsNone(data[0]["issue"])
        self.assertTrue(data[0]["title"].startswith("could not read"))
        self.assertNotIn("url", data[0])

    def test_c5_several_repos_in_order(self):
        gh = FakeGh({"b/two": [issue(5, "B")], "a/one": [issue(9, "A")]})
        code, out = run(["--repo", "b/two", "--repo", "a/one", "--json"], gh)
        self.assertEqual(code, 0)
        self.assertEqual([(i["repo"], i["issue"]) for i in json.loads(out)],
                         [("b/two", 5), ("a/one", 9)])


if __name__ == "__main__":
    unittest.main()
