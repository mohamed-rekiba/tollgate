"""Tollgate's roles ship as Claude Code subagents, written from roles/*.md."""

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
