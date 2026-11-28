"""Tollgate's roles ship as Claude Code subagents, written from roles/*.md."""

import json
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from gate import tickets

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "agents"
ROLES = sorted(p.stem for p in (ROOT / "roles").glob("*.md"))
READ_ONLY = {"analyst", "reviewer", "advisor"}


def frontmatter(text):
    head = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    return dict(line.split(": ", 1) for line in head.group(1).splitlines()), text[head.end():]


class AgentsTest(unittest.TestCase):
    def test_each_role_ships_as_an_agent_written_from_its_role_file(self):
        self.assertEqual(sorted(p.stem for p in AGENTS.glob("*.md")), ROLES)
        for role in ROLES:
            with self.subTest(role=role):
                fields, body = frontmatter((AGENTS / f"{role}.md").read_text())
                self.assertEqual(fields["name"], role)
                self.assertIn((ROOT / "roles" / f"{role}.md").read_text(), body)

    def test_a_read_only_role_cannot_write_and_no_role_starts_another(self):
        for role in ROLES:
            with self.subTest(role=role):
                fields, _ = frontmatter((AGENTS / f"{role}.md").read_text())
                tools = set(fields["tools"].split(", "))
                self.assertNotIn("Agent", tools)
                if role in READ_ONLY:
                    self.assertEqual(tools, {"Read", "Grep", "Glob"})
                else:
                    self.assertIn("Edit", tools)

    def test_no_agent_is_picked_for_ordinary_work(self):
        for role in ROLES:
            with self.subTest(role=role):
                fields, _ = frontmatter((AGENTS / f"{role}.md").read_text())
                self.assertIn("Only when Tollgate's driver names this role", fields["description"])

    def test_each_agent_has_a_turn_limit_and_the_builder_the_highest(self):
        turns = {}
        for role in ROLES:
            fields, _ = frontmatter((AGENTS / f"{role}.md").read_text())
            turns[role] = int(fields["maxTurns"])
        self.assertEqual(max(turns, key=turns.get), "builder")
        for role in READ_ONLY:
            self.assertLess(turns[role], turns["test_writer"])
        self.assertLess(turns["test_writer"], turns["builder"])

    def test_each_agent_knows_its_turn_budget_and_keeps_turns_for_its_answer(self):
        # A subagent that hits its limit ends with a part of its answer and no json block.
        for role in ROLES:
            fields, body = frontmatter((AGENTS / f"{role}.md").read_text())
            with self.subTest(role=role):
                self.assertIn(f"You have at most {fields['maxTurns']} turns.", body)
                self.assertIn("When about 5 of them are left, stop and write your answer", body)

    def test_the_agents_match_the_roles(self):
        result = subprocess.run([sys.executable, "-m", "setup.agents", "--check"], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()


def fenced_blocks(text):
    """Each fenced block of a prompt, without its indent."""
    return [textwrap.dedent(b) for b in re.findall(r"^[ \t]*```[a-z]*\n(.*?)^[ \t]*```", text,
                                                   re.DOTALL | re.MULTILINE)]


class PromptsMatchTheGateTest(unittest.TestCase):
    """The prompts take the ticket rules from gate/tickets.py, so the two cannot drift."""

    def read(self, path):
        return (ROOT / path).read_text()

    def test_the_planner_names_the_cap_and_every_kind(self):
        text = self.read("roles/builder.md")
        self.assertIn(f"{tickets.MIN_ITEMS} to {tickets.MAX_ITEMS} checklist items", text)
        for kind in tickets.KINDS:
            with self.subTest(kind=kind):
                self.assertIn(f"`{kind}`", text)
        for words in ("## Not covered", "fixes:"):
            self.assertIn(words, text)

    def test_the_planner_s_example_ticket_passes_the_gate(self):
        examples = [b for b in fenced_blocks(self.read("roles/builder.md")) if "## Checklist" in b]
        self.assertEqual(len(examples), 1)
        ticket = tickets.parse(examples[0])
        keeps = [i for i in ticket.items if i.keeps_behavior]
        self.assertTrue(keeps, "the example ticket needs a keeps behavior item")
        self.assertTrue(all(i.must for i in keeps))

    def test_the_planner_says_a_keeps_behavior_item_is_a_must_have(self):
        self.assertIn("`[C7, must, keeps behavior]`", self.read("roles/builder.md"))

    def test_the_example_s_keeps_behavior_item_names_its_tests_in_a_locked_file(self):
        examples = [b for b in fenced_blocks(self.read("roles/builder.md")) if "## Checklist" in b]
        ticket = tickets.parse(examples[0])
        for item in (i for i in ticket.items if i.keeps_behavior):
            named = re.findall(r"(\S+\.py)::(test_\w+)", item.text)
            self.assertTrue(named, item.id)
            for path, _ in named:
                self.assertIn(path, ticket.tests)

    def test_the_fix_round_marks_built_behavior_as_keeps_behavior(self):
        text = self.read("roles/builder.md")
        fix = text.split("### A fix round", 1)[1].split("\n## ", 1)[0]
        self.assertIn("already built", fix)
        lines = [m for m in (tickets.ITEM.match(line.strip()) for line in fix.splitlines()) if m]
        marks = [{x.strip() for x in m.group(2).split(",") if x.strip()} for m in lines]
        self.assertIn({"must", "keeps behavior"}, [m - set(tickets.KINDS) for m in marks])
        self.assertIn({"must"}, [m - set(tickets.KINDS) for m in marks])

    def test_a_file_the_project_s_checks_require_is_planned_and_never_out_of_scope(self):
        self.assertIn("a file that the project's own checks require", self.read("roles/builder.md"))
        for lens in ("review", "readiness"):
            with self.subTest(lens=lens):
                self.assertIn("a file that a check of the project requires",
                              self.read(f"lenses/{lens}.md"))

    def test_the_fix_round_s_planner_knows_its_copy_holds_the_built_change(self):
        fix = self.read("roles/builder.md").split("### A fix round", 1)[1].split("\n## ", 1)[0]
        self.assertIn("your copy holds the change that the tickets built", fix)

    def test_the_test_writer_maps_existing_tests_and_never_renames_them(self):
        text = self.read("roles/test_writer.md")
        self.assertIn("never rename", text)
        answer = json.loads(fenced_blocks(text.split("## Answer")[1])[0])
        self.assertTrue(any(not tickets.item_of_test(t["name"]) for t in answer["tests"]))

    def test_the_test_writer_defines_every_kind(self):
        text = self.read("roles/test_writer.md")
        for kind in tickets.KINDS:
            with self.subTest(kind=kind):
                self.assertRegex(text, rf"\n[ \t]*- `{kind}`: \S")

    def test_the_lenses_check_the_kinds(self):
        self.assertIn("kind", self.read("lenses/test_fit.md"))
        readiness = self.read("lenses/readiness.md")
        for words in ("Not covered", "fixes:", "kind"):
            self.assertIn(words, readiness)


class DecisionRecordTest(unittest.TestCase):
    """The prompts, the lenses, and the docs agree on how a decision record works."""

    SECTIONS = ("Status", "Decision", "Why", "Cost", "Where")

    def read(self, path):
        return (ROOT / path).read_text()

    def test_the_docs_skill_gives_the_format_and_the_rule_for_a_change(self):
        text = self.read("skills/docs/SKILL.md")
        self.assertIn("## A decision", text)
        self.assertIn("NNNN-short-title.md", text)
        self.assertIn("`docs/adr`", text)
        self.assertIn("superseded by NNNN", text)
        self.assertIn("Never edit its Decision", text)
        for name in self.SECTIONS:
            with self.subTest(section=name):
                self.assertIn(f"`## {name}`", text)

    def test_the_sections_come_in_the_same_order_in_the_skill_and_the_word_list(self):
        text = self.read("skills/docs/SKILL.md")
        found = re.findall(r"^- `## (\w+)`", text, re.MULTILINE)
        self.assertEqual(found, list(self.SECTIONS))
        self.assertIn("Status, Decision, Why, Cost, and Where", self.read("CONTEXT.md"))

    def test_the_analyst_counts_only_an_accepted_record_inside_spec(self):
        role = self.read("roles/analyst.md")
        for words in ("decision record", "inside a path of `spec`", "`accepted`",
                      "outside `spec` stays assumed"):
            with self.subTest(words=words):
                self.assertIn(words, role)

    def test_the_readiness_lens_holds_the_record_rule_in_item_10(self):
        lens = self.read("lenses/readiness.md")
        item = re.search(r"^10\. .*$", lens, re.MULTILINE).group(0)
        self.assertIn("decision record", item)
        self.assertIn("`create <path>`", item)
        self.assertNotRegex(lens, r"^11\. ", "the rule belongs in item 10, not in a new item")

    def test_the_builder_and_the_review_lens_keep_an_old_decision_unedited(self):
        self.assertIn("never change its Decision", self.read("roles/builder.md"))
        self.assertIn("only its Status line may change", self.read("lenses/review.md"))

    def test_the_analyze_skill_gives_the_spec_paths_to_the_analyst_and_the_check(self):
        text = self.read("skills/analyze/SKILL.md")
        self.assertIn("gate.settings", text)
        self.assertIn("--spec <path>", text)

    def test_the_word_list_defines_a_decision_record_and_the_spec_setting_names_its_folder(self):
        text = self.read("CONTEXT.md")
        self.assertIn("**decision record**:", text)
        self.assertIn("List the folder of decision records in `spec`.", text)
        self.assertIn("List the folder of decision records in `spec`", self.read("docs/design.md"))


class AfterTaskRecordTest(unittest.TestCase):
    """A plan that adds behavior writes it into the spec docs, so the next analysis finds it."""

    WHAT = "what the feature is, how it works, and why it exists"

    def read(self, path):
        return (ROOT / path).read_text()

    def test_the_builder_lists_a_spec_doc_in_the_ticket_that_adds_the_behavior(self):
        text = self.read("roles/builder.md")
        for words in ("adds behavior that no specified fact describes",
                      "in the ticket that adds the behavior", "`modify <path>`", "`create <path>`",
                      self.WHAT):
            with self.subTest(words=words):
                self.assertIn(words, text)

    def test_the_agent_carries_the_same_rule(self):
        self.assertIn(self.WHAT, self.read("agents/builder.md"))

    def test_the_docs_skill_and_the_builder_say_the_same_three_things(self):
        self.assertIn(self.WHAT, self.read("skills/docs/SKILL.md"))
        self.assertIn("**A record of a feature:**", self.read("skills/docs/SKILL.md"))

    def test_the_readiness_lens_holds_the_rule_in_item_10_and_adds_no_item(self):
        lens = self.read("lenses/readiness.md")
        item = re.search(r"^10\. .*$", lens, re.MULTILINE).group(0)
        self.assertIn("adds behavior that no specified fact describes", item)
        self.assertIn("no ticket lists a spec doc under Files", item)
        self.assertNotRegex(lens, r"^11\. ")

    def test_the_review_lens_counts_a_feature_that_no_spec_doc_describes(self):
        item = re.search(r"^9\. .*$", self.read("lenses/review.md"), re.MULTILINE).group(0)
        self.assertIn("adds behavior that none of them describes", item)

    def test_the_design_and_the_word_list_state_it(self):
        self.assertIn("must list a spec doc under Files", self.read("docs/design.md"))
        self.assertIn("a plan that adds behavior writes it into them", self.read("CONTEXT.md"))
