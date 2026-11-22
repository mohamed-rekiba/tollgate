"""Tests for the plugin manifest and the catalog."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def hook_problems(root: Path) -> list:
    """What is wrong with the scripts that hooks/hooks.json names."""
    import os
    import re
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())["hooks"]
    problems = []
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                scripts = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"'\s]+)", hook["command"])
                if not scripts:
                    problems.append(f"{hook['command']} names no script in the plugin")
                for script in scripts:
                    if not (root / script).is_file():
                        problems.append(f"{script} is missing")
                    elif not os.access(root / script, os.X_OK):
                        problems.append(f"{script} is not executable")
    return problems


def load(name):
    return json.loads((ROOT / ".claude-plugin" / name).read_text())


class PluginManifestTest(unittest.TestCase):
    def test_catalog_lists_the_plugin_by_its_manifest_name(self):
        manifest = load("plugin.json")
        catalog = load("marketplace.json")
        names = [entry["name"] for entry in catalog["plugins"]]
        self.assertEqual(names, [manifest["name"]])

    def test_catalog_name_differs_from_plugin_name(self):
        # Another plugin is named tollgate. A different catalog name keeps the
        # install name, tollgate@<catalog>, distinct.
        self.assertNotEqual(load("marketplace.json")["name"], "tollgate")

    def test_every_skill_has_a_name_and_a_description(self):
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            head = skill.read_text().split("---")[1]
            self.assertIn("name:", head, skill)
            self.assertIn("description:", head, skill)

    def test_no_skill_description_holds_angle_brackets(self):
        # Claude Code warns on them, and claude.ai stores the description without them.
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            head = skill.read_text().split("---")[1]
            self.assertNotRegex(head, "[<>]", skill)

    def test_one_description_in_the_manifest_the_catalog_and_the_package(self):
        import re
        text = load("plugin.json")["description"]
        self.assertEqual(load("marketplace.json")["plugins"][0]["description"], text)
        pyproject = (ROOT / "pyproject.toml").read_text()
        self.assertEqual(re.search(r'description = "([^"]*)"', pyproject).group(1), text)
        self.assertNotIn("GitHub", text)

    def test_the_hooks_name_scripts_that_exist_and_run(self):
        self.assertTrue((ROOT / "hooks" / "hooks.json").is_file())
        self.assertEqual(hook_problems(ROOT), [])

    def test_a_missing_or_plain_script_is_a_problem(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "hooks").mkdir()
            (root / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [
                    {"type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/a.py"'},
                    {"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/b.py"}]}]}}))
            (root / "hooks" / "a.py").write_text("print()\n")
            self.assertEqual(hook_problems(root), ["hooks/a.py is not executable",
                                                   "hooks/b.py is missing"])

    def test_no_skill_sends_the_user_to_github(self):
        import re
        bad = re.compile(r"github|\bgh\b|pull request|workflow|\bissues?\b", re.IGNORECASE)
        for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
            self.assertIsNone(bad.search(skill.read_text()), skill)


if __name__ == "__main__":
    unittest.main()
