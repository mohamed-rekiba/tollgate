"""Locked tests for the ticket ruleset-personal."""

import unittest

from setup import apply_rulesets
from tests.test_setup import FakeGh


def tag_ruleset(*args):
    return apply_rulesets.wanted(*args)[1]


class RulesetPersonal(unittest.TestCase):
    def test_c1_personal_account_has_no_creation_rule_or_bypass(self):
        tags = tag_ruleset("User")
        self.assertEqual([r["type"] for r in tags["rules"]], ["update", "deletion"])
        self.assertEqual(tags["bypass_actors"], [])

    def test_c2_tag_pattern_reaches_every_level(self):
        self.assertEqual(tag_ruleset()["conditions"]["ref_name"]["include"],
                         ["refs/tags/tg/**/*"])

    def test_c3_added_fields_are_not_a_change(self):
        gh = FakeGh()
        apply_rulesets.apply(gh, "o/r")
        for ruleset in gh.rulesets.values():
            for rule in ruleset["rules"]:
                if "parameters" in rule:
                    rule["parameters"] = {**rule["parameters"], "added_by_github": True}
        self.assertEqual(apply_rulesets.apply(gh, "o/r"),
                         ["tollgate main: already in place", "tollgate tags: already in place"])

    def test_c4_organization_keeps_creation_rule_and_bypass(self):
        tags = tag_ruleset()
        self.assertEqual(tags["rules"][0], {"type": "creation"})
        self.assertEqual(tags["bypass_actors"][0]["actor_type"], "Integration")
