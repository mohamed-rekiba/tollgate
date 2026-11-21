"""Tests for the approval answer the workflow reads before the tests run."""

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from action import approval
from action import settings as st

SHA = "a" * 40
ROOT = Path(__file__).resolve().parent.parent


class FakeServer:
    def __init__(self, approvals, author="author"):
        self._approvals = approvals
        self.author = author

    def pull(self, pr):
        return {"author": self.author, "head": SHA}

    def approvals(self, pr):
        return self._approvals


def comment(user, body, user_type="User"):
    return {"kind": "comment", "user": user, "user_type": user_type, "state": "",
            "commit": "", "body": body}


def review(user, commit=SHA, state="APPROVED", association="NONE"):
    return {"kind": "review", "user": user, "user_type": "User", "state": state,
            "commit": commit, "body": "", "association": association}


SETTINGS = st.parse(json.dumps({"approvers": ["owner"]}))


class IsApprovedTest(unittest.TestCase):
    def answer(self, approvals, author="author"):
        return approval.is_approved(FakeServer(approvals, author), SETTINGS, 7, SHA)

    def test_an_approver_comment_on_this_commit(self):
        self.assertTrue(self.answer([comment("owner", f"tollgate approve {SHA}")]))

    def test_a_comment_on_another_commit_or_by_a_stranger(self):
        self.assertFalse(self.answer([comment("owner", f"tollgate approve {'b' * 40}")]))
        self.assertFalse(self.answer([comment("stranger", f"tollgate approve {SHA}")]))
        self.assertFalse(self.answer([comment("owner", f"tollgate approve {SHA}", "Bot")]))

    def test_a_review_by_an_approver_or_a_collaborator(self):
        self.assertTrue(self.answer([review("owner")]))
        self.assertTrue(self.answer([review("someone", association="COLLABORATOR")]))

    def test_a_review_that_does_not_count(self):
        self.assertFalse(self.answer([review("owner", commit="b" * 40)]))
        self.assertFalse(self.answer([review("owner", state="COMMENTED")]))
        self.assertFalse(self.answer([review("someone")]))
        self.assertFalse(self.answer([review("owner")], author="owner"))


class MainTest(unittest.TestCase):
    """The command the workflow runs: settings from a checkout of main, answer on stdout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def commit_settings(self, text):
        Path(self.repo, ".tollgate").mkdir(exist_ok=True)
        Path(self.repo, st.PATH).write_text(text)
        for args in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit",
                                     "-q", "-m", "settings"]):
            subprocess.run(["git", *args], cwd=self.repo, check=True)

    def run_main(self, server):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("action.server.Server", return_value=server), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = approval.main(["--repo", str(self.repo), "--repository", "o/r",
                                  "--pr", "7", "--sha", SHA])
        return code, out.getvalue()

    def test_prints_true_or_false(self):
        self.commit_settings(json.dumps({"approvers": ["owner"]}))
        yes = FakeServer([comment("owner", f"tollgate approve {SHA}")])
        self.assertEqual(self.run_main(yes), (0, "true\n"))
        self.assertEqual(self.run_main(FakeServer([])), (0, "false\n"))

    def test_bad_settings_print_nothing_and_fail(self):
        self.commit_settings('{"approvers": ["owner"], "sandbox": "open"}')
        yes = FakeServer([comment("owner", f"tollgate approve {SHA}")])
        self.assertEqual(self.run_main(yes), (1, ""))

    def test_a_github_error_prints_nothing_and_fails(self):
        self.commit_settings(json.dumps({"approvers": ["owner"]}))
        broken = mock.Mock(pull=mock.Mock(side_effect=RuntimeError("no network")))
        self.assertEqual(self.run_main(broken), (1, ""))


class WorkflowTest(unittest.TestCase):
    def test_the_find_job_asks_the_module_and_reads_only_main(self):
        job = yaml.safe_load((ROOT / "workflows/tollgate.yml").read_text())["jobs"]["find"]
        script = next(s["run"] for s in job["steps"] if s.get("id") == "pr")
        self.assertIn("-m action.approval", script)
        self.assertNotIn("reviews", script)
        self.assertNotIn("comments", script)
        self.assertIn('[[ "$answer" == true ]] && approved=true', script)
        refs = [s["with"]["ref"] for s in job["steps"]
                if s.get("uses", "").startswith("actions/checkout") and "repository" not in s["with"]]
        self.assertEqual(refs, ["main"])


if __name__ == "__main__":
    unittest.main()
