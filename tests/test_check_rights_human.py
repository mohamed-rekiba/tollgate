import io
import json
import unittest
from contextlib import redirect_stdout

from setup import check_rights
from setup.gh import GhError


class FakeGh:
    def __init__(self, permissions, allowed="all", error=None):
        self.permissions = permissions
        self.allowed = allowed
        self.error = error

    def get(self, path):
        if self.error:
            raise self.error
        if path.endswith("/actions/permissions"):
            return {"allowed_actions": self.allowed}
        return {"permissions": self.permissions}


def run(argv, gh):
    out = io.StringIO()
    with redirect_stdout(out):
        code = check_rights.main(argv, gh)
    return code, out.getvalue()


ADMIN = {"admin": True, "push": True}
WRITE = {"push": True}


class HumanTests(unittest.TestCase):
    def test_c1_sentence_admin(self):
        self.assertEqual(
            check_rights.sentence({"level": "admin", "reason": "you can set rulesets"}),
            "admin: you can set rulesets.")

    def test_c2_human_prints_sentence_and_returns_zero(self):
        cases = [
            (FakeGh(ADMIN), "admin: you can set rulesets.\n"),
            (FakeGh(WRITE), "write: you can push but cannot set rulesets.\n"),
            (FakeGh(WRITE, allowed="local_only"), "copy: the repository allows only local actions.\n"),
        ]
        for gh, expected in cases:
            with self.subTest(expected=expected):
                code, out = run(["o/r", "--human"], gh)
                self.assertEqual(code, 0)
                self.assertEqual(out, expected)

    def test_c3_human_none_returns_one(self):
        code, out = run(["o/r", "--human"], FakeGh({}))
        self.assertEqual(code, 1)
        self.assertEqual(out, "none: you have no write access.\n")

    def test_c4_human_gh_error(self):
        code, out = run(["o/r", "--human"], FakeGh({}, error=GhError(404, "not found")))
        self.assertEqual(code, 1)
        self.assertEqual(out, "none: not found.\n")

    def test_c4_no_double_period(self):
        code, out = run(["o/r", "--human"], FakeGh({}, error=GhError(500, "boom.")))
        self.assertEqual(code, 1)
        self.assertFalse(out.strip().endswith(".."))

    def test_c5_json_unchanged(self):
        for gh, level, expected_code in [
            (FakeGh(ADMIN), "admin", 0),
            (FakeGh(WRITE), "write", 0),
            (FakeGh(WRITE, allowed="local_only"), "copy", 0),
            (FakeGh({}), "none", 1),
        ]:
            with self.subTest(level=level):
                code, out = run(["o/r"], gh)
                self.assertEqual(code, expected_code)
                self.assertEqual(json.loads(out)["level"], level)
                self.assertEqual(out, json.dumps(json.loads(out)) + "\n")
                self.assertEqual(set(json.loads(out)), {"level", "reason"})


if __name__ == "__main__":
    unittest.main()
