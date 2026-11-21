import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from setup import sync_rules


def make_home(root, projects):
    """projects: {name: {file: text} or None for no lenses folder}"""
    Path(root, "home.json").write_text(json.dumps(
        {"projects": [{"name": f"o/{n}", "path": f"projects/{n}"} for n in projects]}))
    lenses = Path(root, "rules", "lenses")
    lenses.mkdir(parents=True)
    (lenses / "a.md").write_text("A")
    for name, files in projects.items():
        base = Path(root, "projects", name)
        base.mkdir(parents=True)
        if files is not None:
            (base / ".tollgate" / "lenses").mkdir(parents=True)
            for f, t in files.items():
                (base / ".tollgate" / "lenses" / f).write_text(t)


class CheckTest(unittest.TestCase):
    def run_check(self, projects):
        with tempfile.TemporaryDirectory() as d:
            make_home(d, projects)
            out = io.StringIO()
            with redirect_stdout(out):
                code = sync_rules.main(["--home", d, "--check"])
            return code, out.getvalue().split()

    def test_all_in_sync_exits_0(self):
        self.assertEqual(self.run_check({"p": {"a.md": "A"}}), (0, []))

    def test_extra_project_lens_is_not_a_difference(self):
        self.assertEqual(self.run_check({"p": {"a.md": "A", "x.md": "X"}}), (0, []))

    def test_lists_changed_and_missing_projects_and_exits_1(self):
        code, names = self.run_check({"same": {"a.md": "A"}, "old": {"a.md": "B"},
                                      "empty": {}, "none": None})
        self.assertEqual((code, names), (1, ["o/old", "o/empty", "o/none"]))

    def test_not_a_home_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sync_rules.main(["--home", d, "--check"]), 2)


if __name__ == "__main__":
    unittest.main()
