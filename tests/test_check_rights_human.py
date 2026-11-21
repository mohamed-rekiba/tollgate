"""Tests for check_rights --human."""

import contextlib
import io
import json
import unittest

from setup import check_rights
from setup.gh import GhError


class FakeGh:
    def __init__(self, permissions, allowed="all", fail=None):
        self.permissions = permissions
        self.allowed = allowed
        self.fail = fail

    def get(self, path):
        if self.fail:
            raise self.fail
        if path.endswith("/actions/permissions"):
            return {"allowed_actions": self.allowed}
        return {"permissions": self.permissions}


ADMIN = {"admin": True, "push": True}
WRITE = {"push": True}
NONE = {}


def run(argv, gh):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = check_rights.main(argv, gh)
    return out.getvalue(), code


class HumanTest(unittest.TestCase):
    def test_c1_sentence_admin(self):
        found = {"level": "admin", "reason": "you can set rulesets"}
        self.assertEqual(check_rights.sentence(found), "admin: you can set rulesets.")

    def test_c2_main_human_admin(self):
        out, _ = run(["o/r", "--human"], FakeGh(ADMIN))
        self.assertEqual(out, "admin: you can set rulesets.\n")

    def test_c3_main_without_flag_json(self):
        out, code = run(["o/r"], FakeGh(ADMIN))
        self.assertEqual(json.loads(out), {"level": "admin", "reason": "you can set rulesets"})
        self.assertEqual(code, 0)

    def test_c4_human_gh_error(self):
        out, code = run(["o/r", "--human"], FakeGh(ADMIN, fail=GhError(500, "boom")))
        self.assertEqual(out, "none: boom.\n")
        self.assertEqual(code, 1)

    def test_c5_human_return_codes(self):
        cases = [(ADMIN, "all", 0), (WRITE, "all", 0), (WRITE, "local_only", 0), (NONE, "all", 1)]
        for perms, allowed, want in cases:
            with self.subTest(perms=perms, allowed=allowed):
                _, code = run(["o/r", "--human"], FakeGh(perms, allowed))
                self.assertEqual(code, want)

    def test_c6_sentence_other_levels(self):
        self.assertEqual(
            check_rights.sentence({"level": "write", "reason": "you can push but cannot set rulesets"}),
            "write: you can push but cannot set rulesets.")
        self.assertEqual(
            check_rights.sentence({"level": "copy", "reason": "the repository allows only local actions"}),
            "copy: the repository allows only local actions.")
        self.assertEqual(
            check_rights.sentence({"level": "none", "reason": "you have no write access"}),
            "none: you have no write access.")


if __name__ == "__main__":
    unittest.main()
