"""Tests for the setup scripts, with a fake GitHub client."""

import contextlib
import io
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

    def main_output(self, argv, gh):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = check_rights.main(argv, gh=gh)
        return code, out.getvalue()

    def test_human_prints_one_sentence(self):
        gh = FakeGh({("GET", "repos/o/r"): {"permissions": {"admin": True}}})
        code, text = self.main_output(["o/r", "--human"], gh)
        self.assertEqual((code, text), (0, "admin: you can set rulesets.\n"))

    def test_default_is_still_json(self):
        gh = FakeGh({("GET", "repos/o/r"): {"permissions": {"admin": True}}})
        code, text = self.main_output(["o/r"], gh)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)["level"], "admin")

    def test_human_for_none_and_errors(self):
        gh = FakeGh({("GET", "repos/o/r"): {"permissions": {"pull": True}}})
        self.assertEqual(self.main_output(["o/r", "--human"], gh),
                         (1, "none: you have no write access.\n"))
        gh = FakeGh({("GET", "repos/o/r"): GhError(404, "not found")})
        code, text = self.main_output(["o/r", "--human"], gh)
        self.assertEqual(code, 1)
        self.assertTrue(text.startswith("none: "))


class WriteWorkflowsTest(unittest.TestCase):
    def test_writes_one_workflow_and_the_version_and_twice_gives_the_same_result(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".github/workflows").mkdir(parents=True)
            Path(d, ".github/workflows/tollgate-gate.yml").write_text("old")
            Path(d, ".tollgate").mkdir()
            Path(d, ".tollgate/settings.json").write_text('{"pass_score": 80}')
            first = write_workflows.write(d, SHA)
            self.assertEqual(first, [".github/workflows/tollgate.yml",
                                     ".github/workflows/tollgate-gate.yml",
                                     ".tollgate/settings.json"])
            self.assertFalse(Path(d, ".github/workflows/tollgate-gate.yml").exists())
            saved = json.loads(Path(d, ".tollgate/settings.json").read_text())
            self.assertEqual(saved, {"pass_score": 80, "version": SHA})
            self.assertEqual(write_workflows.write(d, SHA), [])
            self.assertEqual(write_workflows.write(d, "self"), [".tollgate/settings.json"])

    def test_copy_puts_tollgates_code_in_the_project_and_counts_as_harness(self):
        from action import settings as st
        from action.paths import matches
        with tempfile.TemporaryDirectory() as d:
            changed = write_workflows.write(d, "copy")
            self.assertIn(".tollgate/runner/action/gate.py", changed)
            self.assertTrue(Path(d, ".tollgate/runner/driver/roles.py").exists())
            self.assertTrue(Path(d, ".tollgate/runner/lenses/change.md").exists())
            self.assertFalse(any("__pycache__" in p for p in changed))
            Path(d, ".tollgate/runner/stale.py").write_text("x")
            again = write_workflows.write(d, "copy")
            self.assertEqual(again, [".tollgate/runner/stale.py"])
            self.assertFalse(Path(d, ".tollgate/runner/stale.py").exists())
            harness = st.parse("{}")["harness"]
            self.assertTrue(matches(".tollgate/runner/action/gate.py", harness))
            self.assertEqual(st.parse('{"version": "copy"}')["version"], "copy")

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

    def test_fields_github_adds_do_not_count_as_a_change(self):
        gh = FakeGh()
        apply_rulesets.apply(gh, "o/r")
        rules = gh.rulesets[1]["rules"]
        rules[2] = dict(rules[2], parameters={**rules[2]["parameters"],
                                              "allowed_merge_methods": ["squash"]})
        self.assertEqual(apply_rulesets.apply(gh, "o/r")[0], "tollgate main: already in place")

    def test_updates_a_changed_ruleset(self):
        gh = FakeGh()
        apply_rulesets.apply(gh, "o/r")
        gh.rulesets[1] = dict(gh.rulesets[1], enforcement="disabled")
        self.assertIn("tollgate main: updated", apply_rulesets.apply(gh, "o/r"))

    def test_the_tag_pattern_reaches_every_level_under_tg(self):
        # GitHub uses fnmatch with FNM_PATHNAME; this mimics it for the tag names Tollgate makes.
        import re
        pattern = apply_rulesets.wanted("User")[1]["conditions"]["ref_name"]["include"][0]
        self.assertEqual(pattern, "refs/tags/tg/**/*")
        rx = re.compile("^" + re.escape(pattern).replace(r"\*\*/", "(?:[^/]+/)*")
                        .replace(r"\*", "[^/]*") + "$")
        for tag in ("refs/tags/tg/freeze/T-1/1", "refs/tags/tg/plan/retries/12"):
            self.assertTrue(rx.match(tag), tag)
        self.assertFalse(rx.match("refs/tags/v1.0"))

    def test_a_personal_repository_gets_no_creation_rule_or_app_bypass(self):
        tags = apply_rulesets.wanted("User")[1]
        self.assertEqual([r["type"] for r in tags["rules"]], ["update", "deletion"])
        self.assertEqual(tags["bypass_actors"], [])
        org = apply_rulesets.wanted("Organization")[1]
        self.assertEqual(org["rules"][0], {"type": "creation"})
        self.assertEqual(org["bypass_actors"][0]["actor_type"], "Integration")

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
