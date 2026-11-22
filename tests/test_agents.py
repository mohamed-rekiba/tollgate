"""Tollgate's roles ship as Claude Code subagents, written from roles/*.md."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

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

    def test_the_agents_match_the_roles(self):
        result = subprocess.run([sys.executable, "-m", "setup.agents", "--check"], cwd=ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
