"""Locked tests for the ticket ruleset-fail-closed."""

import contextlib
import io
import unittest

from setup import apply_rulesets
from tests.test_setup import FakeGh


def gh_with(repo_answer):
    gh = FakeGh({("GET", "repos/o/r"): repo_answer})
    original = gh.api

    def api(method, path, body=None):
        if method == "GET" and path == "repos/o/r":
            gh.calls.append((method, path, body))
            return repo_answer
        return original(method, path, body)
    gh.api = api
    return gh


def tag_rules(gh):
    apply_rulesets.apply(gh, "o/r")
    tags = next(r for r in gh.rulesets.values() if r["name"] == apply_rulesets.TAG_RULESET)
    return [r["type"] for r in tags["rules"]]


class RulesetFailClosed(unittest.TestCase):
    def test_c1_unknown_owner_type_gets_the_creation_rule(self):
        self.assertIn("creation", tag_rules(gh_with({"owner": {}})))

    def test_c2_an_empty_answer_does_not_crash(self):
        self.assertIn("creation", tag_rules(gh_with(None)))

    def test_c3_print_for_a_personal_repository_has_no_creation_rule(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            apply_rulesets.main(["o/r", "--print"], gh=gh_with({"owner": {"type": "User"}}))
        self.assertNotIn('"creation"', out.getvalue())
        self.assertIn('"update"', out.getvalue())

    def test_c4_personal_repository_gets_no_creation_rule(self):
        self.assertNotIn("creation", tag_rules(gh_with({"owner": {"type": "User"}})))
