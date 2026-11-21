"""Tests for the plugin manifest and the catalog."""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    unittest.main()
