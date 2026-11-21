"""Tests for the setup scripts, with a fake GitHub client."""

import json
import tempfile
import unittest
from pathlib import Path

from setup import apply_rulesets, check_rights, prove_gate, write_workflows
from setup.gh import GhError

SHA = "1" * 40


class FakeGh:
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []
        self.rulesets = {}

    def get(self, path):
        return self.api("GET", path)

    def api(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/rulesets") and method == "GET":
            return [{"name": r["name"], "id": i} for i, r in self.rulesets.items()]
        if "/rulesets" in path and method == "POST":
            self.rulesets[len(self.rulesets) + 1] = body
            return {}
        if "/rulesets/" in path:
            rid = int(path.rsplit("/", 1)[1])
            if method == "PUT":
                self.rulesets[rid] = body
            return self.rulesets[rid]
        for (m, prefix), answer in self.answers.items():
            if m == method and path.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                return answer() if callable(answer) else answer
        return {}


class CheckRightsTest(unittest.TestCase):
    def run_with(self, permissions, allowed="all"):
        gh = FakeGh({("GET", "repos/o/r/actions"): {"allowed_actions": allowed},
                     ("GET", "repos/o/r"): {"permissions": permissions}})
        return check_rights.level(gh, "o/r")["level"]

    def test_levels(self):
        self.assertEqual(self.run_with({"admin": True, "push": True}), "admin")
        self.assertEqual(self.run_with({"push": True}), "write")
        self.assertEqual(self.run_with({"pull": True}), "none")
        self.assertEqual(self.run_with({"admin": True}, "local_only"), "copy")

    def test_write_user_cannot_read_action_settings(self):
        gh = FakeGh({("GET", "repos/o/r/actions"): GhError(403, "no"),
                     ("GET", "repos/o/r"): {"permissions": {"push": True}}})
        self.assertEqual(check_rights.level(gh, "o/r")["level"], "write")


class WriteWorkflowsTest(unittest.TestCase):
    def test_writes_pinned_files_and_twice_gives_the_same_result(self):
        with tempfile.TemporaryDirectory() as d:
            first = write_workflows.write(d, SHA)
            self.assertEqual(sorted(first), [".github/workflows/tollgate-freeze.yml",
                                             ".github/workflows/tollgate-gate.yml",
                                             ".github/workflows/tollgate-plan.yml",
                                             ".github/workflows/tollgate-review.yml"])
            self.assertEqual(write_workflows.write(d, SHA), [])
            text = Path(d, first[0]).read_text()
            self.assertIn(f"tollgate/action@{SHA}", text)
            self.assertNotIn("__TOLLGATE_REF__", text)

    def test_refuses_a_branch_name_as_pin(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            write_workflows.write(d, "main")


class ApplyRulesetsTest(unittest.TestCase):
    def test_creates_then_leaves_alone(self):
        gh = FakeGh()
        self.assertEqual(apply_rulesets.apply(gh, "o/r"),
                         ["tollgate main: created", "tollgate tags: created"])
        self.assertEqual(apply_rulesets.apply(gh, "o/r"),
                         ["tollgate main: already in place", "tollgate tags: already in place"])

    def test_updates_a_changed_ruleset(self):
        gh = FakeGh()
        apply_rulesets.apply(gh, "o/r")
        gh.rulesets[1] = dict(gh.rulesets[1], enforcement="disabled")
        self.assertIn("tollgate main: updated", apply_rulesets.apply(gh, "o/r"))

    def test_print_shows_both_requests(self):
        text = apply_rulesets.commands("o/r")
        self.assertEqual(text.count("gh api -X POST repos/o/r/rulesets"), 2)
        self.assertIn('"context": "tollgate gate"', text)


class ProveGateTest(unittest.TestCase):
    def setUp(self):
        manifest = {"files": {".tollgate/tickets/P/ticket.md": "x", "tests/test_p.py": "y"}}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, "tests").mkdir()
        Path(self.tmp.name, "tests/test_p.py").write_text("x = 1")
        self.tag_calls = 0

        def tag_ref():
            self.tag_calls += 1
            if self.tag_calls <= 2:
                raise GhError(404, "not yet")
            return {"object": {"sha": "t"}}

        self.gh = FakeGh({
            ("GET", "repos/o/r/git/ref/tags/"): tag_ref,
            ("GET", "repos/o/r/git/tags/t"): {"message": "Freeze\n\n" + json.dumps(manifest)},
            ("POST", "repos/o/r/pulls"): {"number": 9},
        })
        self.git_calls = []

    def git(self, project, *args):
        self.git_calls.append(args)
        return "abc"

    def answer_check(self, conclusion, summary):
        self.gh.answers[("GET", "repos/o/r/commits/abc/check-runs")] = {"check_runs": [
            {"status": "completed", "conclusion": conclusion, "output": {"summary": summary}}]}

    def prove(self):
        return prove_gate.prove(self.gh, "o/r", "P", self.tmp.name, git=self.git,
                                sleep=lambda s: None, seconds=60)

    def test_passes_when_the_gate_fails_on_rule_3(self):
        self.answer_check("failure", "- Rule 3: a locked file changed")
        result = self.prove()
        self.assertEqual(result["proof"], "passed")
        self.assertEqual(result["locked_file"], "tests/test_p.py")
        self.assertEqual(Path(self.tmp.name, "tests/test_p.py").read_text(), "x = 1\n")
        self.assertIn(("PATCH", "repos/o/r/pulls/9", {"state": "closed"}), self.gh.calls)

    def test_fails_when_the_gate_passes(self):
        self.answer_check("success", "Every gate rule passed.")
        self.assertEqual(self.prove()["proof"], "failed")


if __name__ == "__main__":
    unittest.main()
