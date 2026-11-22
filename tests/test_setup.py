"""Tests for setup: the pre-commit checks, init, merge, the inbox, the home, and health.

Each runs in a temporary git repository, with the state folder and the keys in
temporary folders. The store is a fake here: its bodies belong to the store stream.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import sign, state
from setup import (
    check_commit_msg,
    check_locked,
    check_merge,
    health,
    home,
    inbox,
    merge,
    precommit,
    sync_rules,
)
from setup import init as setup_init

HAS_PRECOMMIT = shutil.which("pre-commit") is not None


def sh(cwd, *args, check=True, env=None):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True, env=env)



# Every tool counts as installed, so the tests do not depend on the machine they run on.
FOUND = lambda tool: "/usr/bin/" + tool

class Env(unittest.TestCase):
    """A temporary state folder, key folder, and owner key."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # A git identity, since a CI machine may have none and every commit needs one.
        patch = mock.patch.dict(os.environ, {"TOLLGATE_STATE": str(self.tmp / "state"),
                                             "TOLLGATE_KEYS": str(self.tmp / "keys"),
                                             "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@t",
                                             "GIT_COMMITTER_NAME": "Test",
                                             "GIT_COMMITTER_EMAIL": "t@t"})
        patch.start()
        self.addCleanup(patch.stop)
        # Docker is checked on its own, in DockerCheckTest.
        docker = mock.patch.object(setup_init, "docker_ready", return_value="")
        docker.start()
        self.addCleanup(docker.stop)
        self.addCleanup(self._tmp.cleanup)
        self.owner = self.tmp / "owner_key"
        sh(self.tmp, "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "owner", "-f",
           str(self.owner))

    def repo(self, name="project") -> Path:
        root = self.tmp / name
        root.mkdir()
        sh(root, "git", "init", "-q", "-b", "main")
        sh(root, "git", "config", "user.email", "owner@example.com")
        sh(root, "git", "config", "user.name", "Owner")
        sh(root, "git", "config", "commit.gpgsign", "false")
        (root / "README.md").write_text("# Shop\n\nShop sells books.\n")
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-q", "-m", "docs(readme): start")
        return root

    def setup_project(self, name="project", install=False) -> Path:
        root = self.repo(name)
        setup_init.init(str(root), f"{self.owner}.pub", install=install, which=FOUND)
        return root

    def branch(self, root, name, files, message=None, verify=False) -> str:
        sh(root, "git", "checkout", "-q", "-b", name, "main")
        for path, text in files.items():
            Path(root, path).parent.mkdir(parents=True, exist_ok=True)
            Path(root, path).write_text(text)
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-q", *([] if verify else ["--no-verify"]), "-m",
           message or f"feat({name}): add {name}")
        head = sh(root, "git", "rev-parse", "HEAD").stdout.strip()
        sh(root, "git", "checkout", "-q", "main")
        return head

    def record_pass(self, root, commit, tier=2):
        path = state.path(str(root), "passes", f"{commit}.json")
        sign.write(path, {"commit": commit, "ticket": "t1", "tier": tier, "lock_sha256": "x",
                          "checks": {"tests": True}, "score": 100, "at": "now"}, "tollgate-pass")

    def record_approval(self, root, commit, key=None):
        path = state.path(str(root), "approvals", f"{commit}.json")
        sign.write(path, {"commit": commit, "ticket": "t1", "approver": "owner", "at": "now"},
                   "tollgate-approval", key=str(key or self.owner))


class FakeStore:
    """The store's checks, done with the shared signing module."""

    def __init__(self, project):
        self.project = project
        self.marked = []

    def _settings(self):
        return json.loads(sh(self.project, "git", "show", "main:.tollgate/settings.json").stdout)

    def passed(self, commit):
        try:
            return sign.read(state.path(self.project, "passes", f"{commit}.json"),
                             "tollgate-pass", self._settings()["signers"])
        except sign.SignError:
            return None

    def approvals(self, commit):
        try:
            return [sign.read(state.path(self.project, "approvals", f"{commit}.json"),
                              "tollgate-approval", self._settings()["owners"])]
        except sign.SignError:
            return []

    def merge(self, commit):
        sh(self.project, "git", "merge", "-q", "--no-ff", "-m", f"chore(merge): {commit[:8]}",
           commit)
        return sh(self.project, "git", "rev-parse", "HEAD").stdout.strip()

    def ready(self, branch, ticket):
        self.marked.append((branch, ticket))


class StateCopyTest(Env):
    def test_the_copy_of_the_state_path_agrees_with_gate_state(self):
        for project in ("/a/shop", str(self.tmp), "/a/b/../shop"):
            self.assertEqual(check_merge.state_dir(project), state.state_dir(project))
        self.assertEqual(check_merge.key_dir(), state.key_dir())
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": "/x", "XDG_CONFIG_HOME": "/y"}):
            os.environ.pop("TOLLGATE_STATE")
            os.environ.pop("TOLLGATE_KEYS")
            self.assertEqual(check_merge.state_dir("/a/shop"), state.state_dir("/a/shop"))
            self.assertEqual(check_merge.key_dir(), state.key_dir())

    def test_the_copy_of_verify_agrees_with_gate_sign(self):
        pub = sign.ensure_key()
        data = b"record\n"
        sig = sign.sign(data, "tollgate-pass")
        self.assertTrue(check_merge.verify(data, sig, "tollgate-pass", [pub]))
        self.assertFalse(check_merge.verify(data, sig, "tollgate-approval", [pub]))
        self.assertFalse(check_merge.verify(b"other\n", sig, "tollgate-pass", [pub]))

    def test_a_worktree_of_the_project_reads_the_same_state(self):
        root = self.repo()
        sh(root, "git", "worktree", "add", "-q", str(self.tmp / "builder"))
        self.assertEqual(check_merge.project_root(self.tmp / "builder"), str(root))


class CommitMsgTest(unittest.TestCase):
    def test_a_good_subject_passes(self):
        self.assertEqual(check_commit_msg.problems("feat(shop): add a cart\n\nWhy.\n"), [])

    def test_a_bad_subject_or_an_ai_credit_fails(self):
        self.assertEqual(len(check_commit_msg.problems("Fixed stuff\n")), 1)
        self.assertEqual(len(check_commit_msg.problems("fix: no scope\n")), 1)
        found = check_commit_msg.problems("fix(a): b\n\nCo-Authored-By: Claude <x@anthropic.com>")
        self.assertIn("credits an AI", found[0])

    def test_a_merge_subject_passes_only_in_a_merge(self):
        self.assertEqual(check_commit_msg.problems("Merge branch 'x'\n", in_merge=True), [])
        self.assertEqual(len(check_commit_msg.problems("Merge branch 'x'\n")), 1)

    def test_comments_and_the_diff_are_not_the_message(self):
        text = "# Fixed stuff\nfeat(a): b\n" + check_commit_msg.SCISSORS + "\nCo-authored-by: claude"
        self.assertEqual(check_commit_msg.problems(text), [])

    def test_it_agrees_with_the_writing_check(self):
        from setup import check_writing
        self.assertEqual(check_commit_msg.SUBJECT.pattern, check_writing.SUBJECT.pattern)


class LockedTest(Env):
    def setUp(self):
        super().setUp()
        self.root = self.setup_project()
        lock = state.path(str(self.root), "locks", "t1.json")
        lock.write_text(json.dumps({"ticket": "t1", "manifest": {"files": {"tests/test_a.py": "x"}}}))

    def stage(self, path, text="x = 1\n"):
        Path(self.root, path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.root, path).write_text(text)
        sh(self.root, "git", "add", path)

    def test_a_change_to_code_passes(self):
        self.stage("src/a.py")
        self.assertEqual(check_locked.check(str(self.root)), [])

    def test_a_change_to_a_locked_test_fails(self):
        self.stage("tests/test_a.py")
        self.assertIn("is locked", check_locked.check(str(self.root))[0])

    def test_a_change_under_tollgate_or_to_the_config_fails(self):
        self.stage(".tollgate/tickets/t2/ticket.md")
        self.stage(".pre-commit-config.yaml", "repos: []\n")
        self.assertEqual(len(check_locked.check(str(self.root))), 2)

    def test_a_merge_of_a_commit_that_passed_may_change_them(self):
        commit = self.branch(self.root, "t1", {"tests/test_a.py": "# test\n"})
        sh(self.root, "git", "merge", "--no-ff", "--no-commit", "--no-verify", commit)
        self.assertNotEqual(check_locked.check(str(self.root)), [])
        self.record_pass(self.root, commit)
        self.assertEqual(check_locked.check(str(self.root)), [])


class MergeCheckTest(Env):
    def setUp(self):
        super().setUp()
        self.root = self.setup_project()
        self.base = sh(self.root, "git", "rev-parse", "HEAD").stdout.strip()

    def test_a_commit_with_a_pass_passes_and_one_without_fails(self):
        commit = self.branch(self.root, "t1", {"src/a.py": "x = 1\n"})
        self.assertIn("no verified pass record", check_merge.check_commit(str(self.root), commit)[0])
        self.record_pass(self.root, commit)
        self.assertEqual(check_merge.check_commit(str(self.root), commit), [])

    def test_tier_3_needs_an_approval_by_an_owner(self):
        commit = self.branch(self.root, "t1", {"src/a.py": "x = 1\n"})
        self.record_pass(self.root, commit, tier=3)
        self.assertIn("no verified approval", check_merge.check_commit(str(self.root), commit)[0])
        self.record_approval(self.root, commit, key=sign.machine_key())
        self.assertIn("no verified approval", check_merge.check_commit(str(self.root), commit)[0])
        self.record_approval(self.root, commit)
        self.assertEqual(check_merge.check_commit(str(self.root), commit), [])

    def test_a_push_of_merges_that_passed_passes(self):
        commit = self.branch(self.root, "t1", {"src/a.py": "x = 1\n"})
        self.record_pass(self.root, commit)
        FakeStore(str(self.root)).merge(commit)
        head = sh(self.root, "git", "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(check_merge.check_push(str(self.root), head, "", "refs/heads/main"), [])

    def test_a_push_of_a_commit_made_on_main_fails(self):
        Path(self.root, "src.py").write_text("x = 1\n")
        sh(self.root, "git", "add", "-A")
        sh(self.root, "git", "commit", "-q", "--no-verify", "-m", "feat(a): direct")
        head = sh(self.root, "git", "rev-parse", "HEAD").stdout.strip()
        found = check_merge.check_push(str(self.root), head, self.base, "refs/heads/main")
        self.assertIn("was made on main", found[0])
        self.assertEqual(check_merge.check_push(str(self.root), head, "", "refs/heads/t1"), [])


class PrecommitTest(Env):
    def test_only_tollgates_checks_for_a_project_with_no_tools(self):
        root = self.repo()
        Path(root, "app.py").write_text("x = 1\n")
        Path(root, "main.go").write_text("package main\n")
        self.assertEqual(precommit.languages(root), ["python", "go"])
        self.assertEqual([h["id"] for h in precommit.tool_hooks(root)], ["gofmt"])

    def test_the_tools_a_project_uses_get_hooks(self):
        root = self.repo()
        Path(root, "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        Path(root, "package.json").write_text('{"devDependencies": {"eslint": "9"}}')
        Path(root, "Cargo.toml").write_text("[package]\n")
        Path(root, "rustfmt.toml").write_text("")
        ids = [h["id"] for h in precommit.tool_hooks(root)]
        self.assertEqual(ids, ["ruff", "eslint", "rustfmt"])

    def test_writes_the_config_and_the_checks_and_twice_changes_nothing(self):
        root = self.repo()
        Path(root, ".tollgate").mkdir()
        Path(root, ".tollgate/settings.json").write_text(json.dumps(
            {"checks": {"tests": {"run": "python3 -m pytest -q"},
                        "writing": {"run": "python3 .tollgate/checks/check_writing.py"}}}))
        changed = precommit.write(str(root))
        self.assertIn(precommit.CONFIG, changed)
        self.assertEqual(len(changed), len(precommit.SCRIPTS) + 1)
        text = Path(root, precommit.CONFIG).read_text()
        self.assertIn("default_install_hook_types: [pre-commit, commit-msg, pre-merge-commit, "
                      "pre-push]", text)
        self.assertIn("tollgate-check-tests", text)
        self.assertNotIn("tollgate-check-writing", text)
        self.assertEqual(precommit.write(str(root)), [])

    def test_refuses_a_config_tollgate_did_not_write(self):
        root = self.repo()
        Path(root, precommit.CONFIG).write_text("repos: []\n")
        with self.assertRaises(precommit.PrecommitError):
            precommit.write(str(root))
        self.assertIn(precommit.CONFIG, precommit.write(str(root), replace=True))

    @unittest.skipUnless(HAS_PRECOMMIT, "pre-commit is not installed")
    def test_pre_commit_runs_the_generated_config(self):
        root = self.setup_project()
        Path(root, "a.py").write_text("x = 1  # one plain comment\n")
        sh(root, "git", "add", "a.py")
        done = sh(root, "pre-commit", "run", check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        Path(root, "a.py").write_text("x = 1  # we leverage this\n")
        sh(root, "git", "add", "a.py")
        done = sh(root, "pre-commit", "run", check=False)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("'leverage' is filler", done.stdout)


@unittest.skipUnless(HAS_PRECOMMIT, "pre-commit is not installed")
class HooksTest(Env):
    """The checks as git runs them, through pre-commit."""

    def setUp(self):
        super().setUp()
        self.root = self.setup_project(install=True)

    def test_a_commit_to_a_locked_file_or_with_a_bad_subject_is_refused(self):
        sh(self.root, "git", "checkout", "-q", "-b", "t1")
        Path(self.root, ".tollgate/settings.json").write_text("{}\n")
        sh(self.root, "git", "add", "-A")
        done = sh(self.root, "git", "commit", "-m", "chore(a): loosen", check=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Tollgate's file", done.stdout + done.stderr)
        sh(self.root, "git", "checkout", "-q", "HEAD", "--", ".tollgate/settings.json")
        Path(self.root, "a.py").write_text("x = 1\n")
        sh(self.root, "git", "add", "-A")
        done = sh(self.root, "git", "commit", "-m", "Fixed stuff", check=False)
        self.assertNotEqual(done.returncode, 0)
        done = sh(self.root, "git", "commit", "-m", "feat(a): add a", check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_merge_into_main_needs_a_pass(self):
        commit = self.branch(self.root, "t1", {"a.py": "x = 1\n"}, verify=True)
        done = sh(self.root, "git", "merge", "--no-ff", "-m", "chore(merge): t1", commit,
                  check=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no verified pass record", done.stdout + done.stderr)
        sh(self.root, "git", "merge", "--abort", check=False)
        self.record_pass(self.root, commit)
        done = sh(self.root, "git", "merge", "--no-ff", "-m", "chore(merge): t1", commit,
                  check=False)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class InitTest(Env):
    def test_init_sets_up_the_project(self):
        root = self.repo()
        lines = setup_init.init(str(root), f"{self.owner}.pub", install=HAS_PRECOMMIT, which=FOUND)
        settings = json.loads(sh(root, "git", "show", "main:.tollgate/settings.json").stdout)
        self.assertEqual(settings["signers"], [sign.ensure_key()])
        self.assertEqual(settings["owners"], [Path(f"{self.owner}.pub").read_text().strip()])
        self.assertIn("writing", settings["checks"])
        self.assertTrue(state.state_dir(str(root)).joinpath("passes").is_dir())
        for name in precommit.SCRIPTS:
            self.assertTrue(Path(root, ".tollgate/checks", name).exists())
        log = sh(root, "git", "log", "-1", "--format=%s").stdout.strip()
        self.assertEqual(log, setup_init.SUBJECT)
        if HAS_PRECOMMIT:
            self.assertTrue(Path(root, ".git/hooks/pre-merge-commit").exists())
            found = health.warnings(str(root), plugin=self.tmp)
            self.assertEqual(len(found), 1)
            self.assertIn("the plugin has no Claude Code hooks", found[0])
        self.assertIn("files: already in place",
                      setup_init.init(str(root), f"{self.owner}.pub", install=False, which=FOUND))
        self.assertTrue(lines)

    def test_init_stops_when_a_tool_is_missing(self):
        root = self.repo()
        with self.assertRaisesRegex(setup_init.InitError, "not installed: claude"):
            setup_init.init(str(root), f"{self.owner}.pub",
                            which=lambda t: None if t == "claude" else "/bin/" + t)

    def test_init_stops_off_main_or_with_the_machine_key(self):
        root = self.repo()
        sh(root, "git", "checkout", "-q", "-b", "other")
        with self.assertRaisesRegex(setup_init.InitError, "not main"):
            setup_init.init(str(root), f"{self.owner}.pub", install=False, which=FOUND)
        sh(root, "git", "checkout", "-q", "main")
        sign.ensure_key()
        with self.assertRaisesRegex(setup_init.InitError, "machine key"):
            setup_init.init(str(root), f"{sign.machine_key()}.pub", install=False, which=FOUND)


REAL_DOCKER_READY = setup_init.docker_ready


class DockerCheckTest(Env):
    def write(self, root, isolation):
        Path(root, ".tollgate").mkdir(exist_ok=True)
        Path(root, ".tollgate/settings.json").write_text(json.dumps(
            {"runner": "background", "isolation": isolation}))

    def test_the_container_isolation_needs_docker(self):
        root = self.repo()
        self.write(root, "container")
        with mock.patch.object(setup_init, "docker_ready", REAL_DOCKER_READY):
            with self.assertRaisesRegex(setup_init.InitError, "docker is not installed"):
                setup_init.check_isolation(root, which=lambda t: None)
            with mock.patch.object(setup_init.subprocess, "run",
                                   return_value=mock.Mock(returncode=1)), \
                    self.assertRaisesRegex(setup_init.InitError, "installed but not running"):
                setup_init.check_isolation(root, which=lambda t: "/bin/" + t)
            with mock.patch.object(setup_init.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)):
                self.assertEqual(setup_init.check_isolation(root, which=lambda t: "/bin/" + t),
                                 "isolation: container, Docker is running")

    def test_session_mode_needs_no_docker(self):
        # No settings means session mode: your own session runs each role.
        root = self.repo()
        with mock.patch.object(setup_init, "docker_ready", REAL_DOCKER_READY):
            self.assertEqual(setup_init.check_isolation(root, which=lambda t: None),
                             "runner: session, Docker not needed")
            Path(root, ".tollgate").mkdir(exist_ok=True)
            Path(root, ".tollgate/settings.json").write_text(json.dumps({"isolation": "container"}))
            self.assertEqual(setup_init.check_isolation(root, which=lambda t: None),
                             "runner: session, Docker not needed")

    def test_the_sandbox_isolation_skips_the_check(self):
        root = self.repo()
        self.write(root, "sandbox")
        with mock.patch.object(setup_init, "docker_ready", REAL_DOCKER_READY):
            self.assertEqual(setup_init.check_isolation(root, which=lambda t: None),
                             "isolation: sandbox, Docker not needed")


class MergeTest(Env):
    def setUp(self):
        super().setUp()
        self.root = self.setup_project()
        self.store = FakeStore(str(self.root))
        self.commit = self.branch(self.root, "t1", {"a.py": "x = 1\n"})

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = merge.main(["--project", str(self.root), *argv], store=self.store)
        return code, out.getvalue() + err.getvalue()

    def test_list_shows_only_changes_that_passed(self):
        self.assertIn("No change is ready", self.run_main("list")[1])
        self.record_pass(self.root, self.commit, tier=3)
        code, out = self.run_main("list")
        self.assertEqual(code, 0)
        self.assertIn("ticket t1  tier 3", out)
        self.assertIn("needs your approval", out)
        self.assertIn("pass  tests", self.run_main("show", self.commit)[1])

    def test_approve_signs_with_the_owners_key_then_merge_merges(self):
        self.record_pass(self.root, self.commit, tier=3)
        self.assertIn("approve it first", self.run_main("merge", self.commit)[1])
        code, out = self.run_main("approve", self.commit, "--key", str(self.owner))
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.store.approvals(self.commit)), 1)
        code, out = self.run_main("merge", self.commit)
        self.assertEqual(code, 0, out)
        sh(self.root, "git", "merge-base", "--is-ancestor", self.commit, "main")

    def test_a_change_made_by_hand_merges_only_after_your_approval(self):
        self.assertIn("a change made by hand", self.run_main("show", self.commit)[1])
        code, out = self.run_main("merge", self.commit)
        self.assertEqual(code, 1)
        self.assertIn("needs your approval first", out)
        code, out = self.run_main("approve", self.commit, "--key", str(self.owner))
        self.assertEqual(code, 0, out)
        code, out = self.run_main("merge", self.commit)
        self.assertEqual(code, 0, out)
        sh(self.root, "git", "merge-base", "--is-ancestor", self.commit, "main")

    def test_approve_refuses_a_ticket_with_no_pass_and_a_key_not_in_owners(self):
        sh(self.root, "git", "branch", "tg/T-1", self.commit)
        self.assertIn("Only the gate passes a ticket",
                      self.run_main("approve", self.commit, "--key", str(self.owner))[1])
        self.record_pass(self.root, self.commit, tier=4)
        other = self.tmp / "other"
        sh(self.tmp, "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other))
        code, out = self.run_main("approve", self.commit, "--key", str(other))
        self.assertEqual(code, 1)
        self.assertIn("not in owners", out)
        self.assertEqual(self.store.approvals(self.commit), [])


class FakeQuestions:
    answers: dict

    def __init__(self, project):
        self.project = project

    def open_questions(self):
        if self.project in self.answers:
            return {}
        return {1: {"n": 1, "title": "Tests fail twice", "body": "", "options": ["retry", "stop"],
                    "answer": None}}

    def answer(self, n, body):
        self.answers[self.project] = body


class InboxTest(unittest.TestCase):
    def test_lists_and_answers_a_question(self):
        FakeQuestions.answers = {}
        found = inbox.inbox(["/p"], FakeQuestions)
        self.assertEqual(found[0]["title"], "Tests fail twice")
        inbox.answer("/p", 1, "retry", "use a smaller step", FakeQuestions)
        self.assertEqual(FakeQuestions.answers["/p"], "retry use a smaller step")
        self.assertEqual(inbox.inbox(["/p"], FakeQuestions), [])

    def test_refuses_an_answer_that_is_not_an_option(self):
        FakeQuestions.answers = {}
        with self.assertRaisesRegex(Exception, "not an option"):
            inbox.answer("/p", 1, "merge", "", FakeQuestions)
        with self.assertRaisesRegex(Exception, "not open"):
            inbox.answer("/p", 2, "retry", "", FakeQuestions)


class HomeTest(Env):
    def test_a_home_adds_a_project_and_sync_makes_a_ready_change(self):
        project = self.setup_project("shop")
        folder = self.tmp / "home"
        folder.mkdir()
        self.assertEqual(home.init(str(folder)), "created")
        added = home.add(str(folder), str(project))
        self.assertEqual((added["name"], added["has_settings"]), ("shop", True))
        Path(folder, "rules/lenses/style.md").write_text("Short names.\n")
        stores = []

        def store(path):
            stores.append(FakeStore(path))
            return stores[-1]

        result = sync_rules.sync(str(folder), store)
        self.assertEqual(result[0]["result"],
                         "the branch tollgate-sync waits for your approval: /tollgate:merge")
        shown = sh(folder / "projects/shop", "git", "show",
                   "tollgate-sync:.tollgate/lenses/style.md").stdout
        self.assertEqual(shown, "Short names.\n")
        self.assertEqual(sync_rules.sync(str(folder), store)[0]["result"],
                         "already a ready change on the branch tollgate-sync")

    def test_a_home_needs_an_empty_folder(self):
        folder = self.tmp / "home"
        folder.mkdir()
        Path(folder, "x").write_text("")
        with self.assertRaises(home.HomeError):
            home.init(str(folder))


class HealthTest(Env):
    def test_a_project_with_no_setup_warns_for_each_part(self):
        root = self.repo()
        found = health.warnings(str(root), which=lambda t: None)
        self.assertIn("pre-commit is not installed", found[0])
        self.assertTrue(any("pre-merge-commit" in w for w in found))
        self.assertTrue(any("check_merge.py is missing" in w for w in found))


if __name__ == "__main__":
    unittest.main()


class OwnChecksTest(unittest.TestCase):
    def test_this_repository_carries_the_same_checks_it_copies_into_a_project(self):
        root = Path(__file__).resolve().parent.parent
        for name in ("check_locked.py", "check_writing.py", "check_commit_msg.py",
                     "check_merge.py"):
            with self.subTest(check=name):
                self.assertEqual((root / ".tollgate/checks" / name).read_text(),
                                 (root / "setup" / name).read_text(),
                                 "run python3 -m setup.precommit after changing a check")
