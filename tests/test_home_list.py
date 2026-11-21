"""`home list` prints a settings column for each project."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from setup import home


def run_list(root):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = home.main(["--home", str(root), "list"])
    return code, out.getvalue().splitlines()


class HomeListTest(unittest.TestCase):
    def make_home(self, projects):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        entries = []
        for name, has_settings in projects:
            path = f"projects/{name.split('/')[1]}"
            Path(root, path).mkdir(parents=True)
            if has_settings:
                Path(root, path, ".tollgate").mkdir()
                Path(root, path, ".tollgate", "settings.json").write_text("{}")
            entries.append({"name": name, "path": path})
        Path(root, home.HOME_FILE).write_text(json.dumps({"projects": entries}))
        return root

    def test_third_column_reports_settings(self):
        root = self.make_home([("o/with", True), ("o/without", False)])
        code, lines = run_list(root)
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["o/with\tprojects/with\tsettings",
                                 "o/without\tprojects/without\tno settings"])

    def test_empty_home_prints_nothing(self):
        code, lines = run_list(self.make_home([]))
        self.assertEqual((code, lines), (0, []))


if __name__ == "__main__":
    unittest.main()
