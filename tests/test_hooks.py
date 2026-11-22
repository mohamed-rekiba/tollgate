"""Tests for the guard hook and the role settings files.

The hook is run as Claude Code runs it: a process with the tool call JSON on
standard input. Exit 0 lets the call run; exit 2 refuses it, with the reason on
standard error.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gate import state
from hooks import policy

GUARD = str(Path(__file__).resolve().parent.parent / "hooks" / "guard.py")
HOOKS_JSON = Path(__file__).resolve().parent.parent / "hooks" / "hooks.json"


class Env(unittest.TestCase):
    """A project, its state folder with one lock, and a builder's copy."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(os.path.realpath(tmp.name))
        self.env = {"TOLLGATE_STATE": str(root / "state"), "TOLLGATE_KEYS": str(root / "keys")}
        patch = mock.patch.dict(os.environ, self.env)
        patch.start()
        self.addCleanup(patch.stop)
        self.project = root / "project"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.project)], check=True)
        self.copy = state.path(str(self.project), "builders", "T-1")
        self.copy.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "tg/T-1", str(self.copy)], check=True)
        lock = {"ticket": "T-1", "manifest": {"files": {"tests/test_t1.py": "sha256:x",
                                                        ".tollgate/tickets/T-1/ticket.md": "x"},
                                              "tests": [], "keeps_behavior": []}}
        state.path(str(self.project), "locks", "T-1.json").write_text(json.dumps(lock))

    def guard(self, tool, tool_input, role="builder", cwd=None, agent_type=None):
        """Run the hook. Return (exit code, standard error). agent_type is what
        Claude Code sends when the call comes from a subagent."""
        cwd = str(cwd or (self.copy if role else self.project))
        call = {"session_id": "s", "transcript_path": "/tmp/t.jsonl", "cwd": cwd,
                "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
        if agent_type:
            call.update(agent_id="a1", agent_type=agent_type)
        args = [sys.executable, GUARD, "--project", str(self.project)]
        if role:
            args += ["--role", role, "--copy", str(self.copy)]
        done = subprocess.run(args, input=json.dumps(call), capture_output=True, text=True,
                              env={**os.environ, **self.env}, check=False)
        return done.returncode, done.stderr

    def assertLets(self, *args, **kw):
        code, err = self.guard(*args, **kw)
        self.assertEqual((code, err), (0, ""))

    def assertRefuses(self, words, *args, **kw):
        code, err = self.guard(*args, **kw)
        self.assertEqual(code, 2, err)
        self.assertIn(words.lower(), err.lower())


class EditTest(Env):
    def test_an_edit_in_the_own_copy_runs(self):
        self.assertLets("Edit", {"file_path": str(self.copy / "app.py"), "old_string": "a",
                                 "new_string": "b"})
        self.assertLets("Write", {"file_path": "app.py", "content": "x"})

    def test_an_edit_of_a_locked_file_is_refused(self):
        self.assertRefuses("locked by ticket T-1", "Write",
                           {"file_path": str(self.copy / "tests/test_t1.py"), "content": "x"})
        self.assertRefuses("locked by ticket T-1", "MultiEdit",
                           {"file_path": "tests/test_t1.py", "edits": []})

    def test_an_edit_under_tollgate_is_refused(self):
        self.assertRefuses("under .tollgate/", "Edit",
                           {"file_path": str(self.copy / ".tollgate/settings.json")})

    def test_a_planner_writes_plans_and_tickets_but_not_settings(self):
        self.assertLets("Write", {"file_path": ".tollgate/plans/demo.md", "content": "x"},
                        role="planner")
        self.assertRefuses("under .tollgate/", "Write",
                           {"file_path": ".tollgate/settings.json", "content": "x"}, role="planner")

    def test_an_edit_in_the_state_folder_outside_the_copy_is_refused(self):
        lock = state.path(str(self.project), "locks", "T-1.json")
        self.assertRefuses("in the state folder", "Write", {"file_path": str(lock), "content": "{}"})
        other = state.path(str(self.project), "builders", "T-2", "app.py")
        self.assertRefuses("in the state folder", "Edit", {"file_path": str(other)})

    def test_an_edit_in_the_key_folder_is_refused(self):
        self.assertRefuses("key folder", "Write",
                           {"file_path": self.env["TOLLGATE_KEYS"] + "/id_ed25519", "content": ""})

    def test_a_role_edits_nothing_outside_its_copy(self):
        self.assertRefuses("outside the role's own copy", "Write",
                           {"file_path": str(self.project / "app.py"), "content": "x"})

    def test_a_notebook_edit_is_checked_too(self):
        self.assertLets("NotebookEdit", {"notebook_path": str(self.copy / "n.ipynb")})
        self.assertRefuses("locked by ticket T-1", "NotebookEdit",
                           {"notebook_path": str(self.copy / "tests/test_t1.py")})


class PersonTest(Env):
    """With no role, the hook guards your own session in the project."""

    def test_you_edit_code_and_write_a_ticket(self):
        self.assertLets("Edit", {"file_path": str(self.project / "app.py")}, role="")
        self.assertLets("Write", {"file_path": ".tollgate/tickets/T-9/ticket.md", "content": "x"},
                        role="")

    def test_you_do_not_edit_a_locked_file_or_the_state_folder(self):
        self.assertRefuses("locked by ticket T-1", "Edit",
                           {"file_path": str(self.project / "tests/test_t1.py")}, role="")
        self.assertRefuses("in the state folder", "Edit",
                           {"file_path": str(self.copy / "app.py")}, role="")


class YourPushTest(Env):
    """Your own session may push a branch for review, but never main."""

    def test_you_push_a_branch(self):
        subprocess.run(["git", "-C", str(self.project), "switch", "-q", "-c", "fix-x"], check=True)
        for command in ("git push -u origin fix-x", "git push", "git push origin",
                        "git push origin HEAD", "git push --force-with-lease origin fix-x"):
            self.assertLets("Bash", {"command": command}, role="")

    def test_you_do_not_push_main(self):
        for command in ("git push origin main", "git push origin HEAD:main",
                        "git push origin fix-x:refs/heads/main", "git push --all",
                        "git push --mirror", "git push origin +main"):
            self.assertRefuses("main", "Bash", {"command": command}, role="")
        # On main, a push with no branch named pushes main.
        self.assertRefuses("main", "Bash", {"command": "git push"}, role="")


class AgentTypeTest(Env):
    """A Tollgate subagent gets its role's rules from the agent type Claude Code sends."""

    def test_a_tollgate_subagent_is_its_role(self):
        for agent_type in ("builder", "tollgate:builder"):
            self.assertRefuses("no role pushes", "Bash", {"command": "git push origin fix-x"},
                               role="", agent_type=agent_type)
        self.assertRefuses("reads only", "Bash", {"command": "ls"}, role="",
                           agent_type="tollgate:reviewer")
        self.assertRefuses("reads only", "Edit", {"file_path": str(self.project / "app.py")},
                           role="", agent_type="tollgate:analyst")

    def test_another_subagent_keeps_your_session_s_rules(self):
        self.assertLets("Edit", {"file_path": str(self.project / "app.py")}, role="",
                        agent_type="Explore")
        self.assertRefuses("locked by ticket T-1", "Edit",
                           {"file_path": str(self.project / "tests/test_t1.py")}, role="",
                           agent_type="general-purpose")


class StepFileTest(Env):
    """In session mode a subagent's copy comes from the step file, run/step.json."""

    def write_step(self, role, policy=None, copy=None):
        step = {"role": role, "policy": policy or role, "copy": str(copy or self.copy),
                "key": "k"}
        state.path(str(self.project), "run", "step.json").write_text(json.dumps(step))

    def edit(self, path="app.py"):
        return "Write", {"file_path": str(self.copy / path), "content": "x"}

    def test_a_subagent_edits_the_copy_the_step_file_names(self):
        self.write_step("builder")
        self.assertLets(*self.edit(), role="", agent_type="tollgate:builder")
        self.assertRefuses("outside the role's own copy", "Write",
                           {"file_path": str(self.project / "app.py"), "content": "x"},
                           role="", agent_type="tollgate:builder")

    def test_a_step_for_another_role_gives_no_copy(self):
        self.write_step("test_writer")
        self.assertRefuses("outside the role's own copy", *self.edit(), role="",
                           agent_type="tollgate:builder")

    def test_with_no_step_file_a_subagent_has_no_copy(self):
        self.assertRefuses("outside the role's own copy", *self.edit(), role="",
                           agent_type="tollgate:builder")

    def test_a_builder_that_writes_a_plan_may_write_plans_in_its_copy(self):
        self.write_step("builder", policy="planner")
        self.assertLets(*self.edit(".tollgate/plans/demo.md"), role="",
                        agent_type="tollgate:builder")
        self.write_step("builder")
        self.assertRefuses("only the driver writes there", *self.edit(".tollgate/plans/demo.md"),
                           role="", agent_type="tollgate:builder")


class KeyAndStateReadTest(Env):
    """A role reads neither the key folder nor the state folder outside its copy."""

    def setUp(self):
        super().setUp()
        self.keys = state.key_dir()
        self.keys.mkdir(parents=True, exist_ok=True)
        (self.keys / "id_ed25519").write_text("secret")
        self.lock = state.path(str(self.project), "locks", "T-1.json")

    def test_a_role_cannot_read_the_key_folder_or_the_state_folder(self):
        for role in ("builder", "reviewer"):
            self.assertRefuses("key folder", "Read", {"file_path": str(self.keys / "id_ed25519")},
                               role=role)
            self.assertRefuses("state folder", "Read", {"file_path": str(self.lock)}, role=role)
            self.assertRefuses("key folder", "Grep", {"pattern": "x", "path": str(self.keys)},
                               role=role)
            self.assertRefuses("state folder", "Glob",
                               {"pattern": "*.json", "path": str(self.lock.parent)}, role=role)
            self.assertRefuses("key folder", "Glob", {"pattern": f"{self.keys}/*"}, role=role)

    def test_a_role_reads_its_own_copy(self):
        self.assertLets("Read", {"file_path": str(self.copy / "app.py")})
        self.assertLets("Grep", {"pattern": "x"})
        self.assertLets("Glob", {"pattern": "**/*.py", "path": str(self.copy)})

    def test_a_subagent_reads_the_copy_of_its_step(self):
        step = {"role": "reviewer", "policy": "reviewer", "copy": str(self.copy), "key": "k"}
        state.path(str(self.project), "run", "step.json").write_text(json.dumps(step))
        self.assertLets("Read", {"file_path": str(self.copy / "app.py")}, role="",
                        agent_type="tollgate:reviewer")
        self.assertRefuses("state folder", "Read",
                           {"file_path": str(state.path(str(self.project), "run", "step.json"))},
                           role="", agent_type="tollgate:reviewer")

    def test_a_role_s_command_may_not_name_the_key_or_the_state_folder(self):
        self.assertRefuses("key folder", "Bash", {"command": f"cat {self.keys}/id_ed25519"})
        self.assertRefuses("state folder", "Bash", {"command": f"cat {self.lock}"})
        self.assertRefuses("key folder", "Bash", {"command": "cat ~/.config/tollgate/id_ed25519"}
                           if str(self.keys).startswith(str(Path.home())) else
                           {"command": f"ls {self.keys}"})
        self.assertLets("Bash", {"command": f"cd {self.copy} && ls"})

    def test_a_role_may_not_run_a_tollgate_command(self):
        root = Path(GUARD).resolve().parent.parent
        for command in ("python3 -m driver.step answer --project . --key k --nonce n",
                        'PYTHONPATH="/x" python3 -P -m setup.inbox --project . answer 1 approve',
                        "python3 -m gate.store", "python3 -m setup.merge",
                        f"python3 {root}/driver/step.py next --task demo",
                        "cd /tmp && python3 driver/task.py",
                        "python3 -c 'from driver import step; step.main()'",
                        'python3 -c "import gate.store"',
                        "python3 -c 'import importlib; importlib.import_module(\"driver.step\")'",
                        "python3 - <<EOF\nfrom setup.inbox import main\nEOF"):
            with self.subTest(command=command):
                self.assertRefuses("tollgate command", "Bash", {"command": command})
                self.assertRefuses("tollgate command", "Bash", {"command": command}, role="",
                                   agent_type="tollgate:builder")
        for command in ("python3 -m unittest", "ruff check gate/store.py", "pytest tests"):
            self.assertLets("Bash", {"command": command})
        # Your own session runs them.
        self.assertLets("Bash", {"command": "python3 -m driver.step next --task demo"}, role="")

    def test_a_role_s_command_may_not_climb_out_of_its_copy(self):
        for command in (f"cat {self.copy}/../../logs/T-1.jsonl", "cat ../../run/step.json",
                        "cd .. && ls", f"echo x > {self.copy}/../../run/step.json",
                        "ls ..", "python3 -c 'open(\"../../run/step.json\")'"):
            with self.subTest(command=command):
                self.assertRefuses("..", "Bash", {"command": command})
        self.assertLets("Bash", {"command": "ls ./tests && echo ...done"})

    def test_your_own_session_may_still_read_the_state_folder(self):
        self.assertLets("Read", {"file_path": str(self.lock)}, role="")


class ReadOnlyTest(Env):
    def test_a_reviewer_reads(self):
        self.assertLets("Read", {"file_path": str(self.copy / "app.py")}, role="reviewer")

    def test_a_reviewer_and_the_advisor_edit_nothing_and_run_nothing(self):
        for role in ("reviewer", "advisor", "analyst"):
            self.assertRefuses("reads only", "Edit", {"file_path": str(self.copy / "app.py")},
                               role=role)
            self.assertRefuses("reads only", "Bash", {"command": "ls"}, role=role)


class BashTest(Env):
    def test_ordinary_commands_run(self):
        for command in ("python3 run_tests.py", "git status && git diff main...HEAD",
                        "git commit -m 'no -n here' -q", "git merge-base main HEAD",
                        "echo push"):
            self.assertLets("Bash", {"command": command})

    def test_a_push_is_refused(self):
        for command in ("git push origin HEAD:main", "cd x && git -C . push",
                        "/usr/bin/git push", "true; git push -f"):
            self.assertRefuses("no role pushes", "Bash", {"command": command})

    def test_a_merge_into_main_is_refused(self):
        self.assertRefuses("only the store merges", "Bash",
                           {"command": "git checkout main && git merge tg/T-1"})
        self.assertRefuses("only the store merges", "Bash", {"command": "git merge tg/T-1"},
                           role="", cwd=self.project)

    def test_a_merge_of_main_into_the_ticket_branch_is_refused_too(self):
        # The command names main, so the hook cannot tell the direction from the words.
        self.assertRefuses("only the store merges", "Bash", {"command": "git merge main"})

    def add_origin(self):
        subprocess.run(["git", "-C", str(self.project), "remote", "add", "origin",
                        str(self.project)], check=True)

    def test_a_fast_forward_from_the_remote_main_is_a_sync(self):
        self.add_origin()
        for command in ("git merge --ff-only origin/main", "git merge --ff-only @{u}",
                        "git checkout main && git merge --ff-only refs/remotes/origin/main"):
            self.assertLets("Bash", {"command": command}, role="", cwd=self.project)

    def test_a_merge_that_is_not_a_sync_is_still_refused(self):
        self.add_origin()
        for command in ("git merge origin/main",             # it may create a merge commit
                        "git merge --ff-only tg/T-1",        # a local branch, not the remote
                        "git merge --ff-only fake/main",     # no remote has that name
                        "git merge --ff-only origin/main tg/T-1"):
            self.assertRefuses("only the store merges", "Bash", {"command": command},
                               role="", cwd=self.project)

    def test_no_verify_is_refused(self):
        for command in ("git commit --no-verify -m x", "git commit -nm x", "git commit -n"):
            self.assertRefuses("skips the checks", "Bash", {"command": command})

    def test_changing_core_hookspath_is_refused(self):
        for command in ("git config core.hooksPath /dev/null",
                        "git -c core.hooksPath=/x commit -m y",
                        "git config --local CORE.HOOKSPATH x"):
            self.assertRefuses("core.hooksPath", "Bash", {"command": command})

    def test_a_call_that_is_not_json_is_refused(self):
        done = subprocess.run([sys.executable, GUARD], input="not json", capture_output=True,
                              text=True, check=False)
        self.assertEqual(done.returncode, 2)
        self.assertIn("could not read", done.stderr)


class HooksJsonTest(unittest.TestCase):
    def test_the_plugin_runs_the_guard_before_edits_and_commands(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]["PreToolUse"]
        self.assertEqual(hooks[0]["matcher"],
                         "Edit|Write|MultiEdit|NotebookEdit|Bash|Read|Grep|Glob")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/guard.py", hooks[0]["hooks"][0]["command"])


class PolicyTest(Env):
    """The settings file of each role. UNTESTED with Claude Code itself."""

    def rules(self, role):
        return policy.settings_for(role, str(self.copy), str(self.project))

    def test_the_builder_and_the_test_writer_edit_only_their_copy(self):
        for role in ("builder", "test_writer"):
            p = self.rules(role)["permissions"]
            self.assertIn(f"Edit(/{self.copy}/**)", p["allow"])
            self.assertIn("Bash", p["allow"])
            self.assertFalse([r for r in p["allow"] if r.startswith("Edit(")
                              and not r.startswith(f"Edit(/{self.copy}")])

    def test_the_builder_may_not_edit_locked_files_tollgate_or_the_state(self):
        deny = self.rules("builder")["permissions"]["deny"]
        self.assertIn(f"Edit(/{self.copy}/tests/test_t1.py)", deny)
        self.assertIn(f"Edit(/{self.copy}/.tollgate/**)", deny)
        locks = state.state_dir(str(self.project)) / "locks"
        self.assertIn(f"Edit(/{locks}/**)", deny)
        self.assertIn(f"Read(/{self.env['TOLLGATE_KEYS']}/**)", deny)
        for command in ("git push", "git merge", "git commit --no-verify",
                        "git config core.hooksPath"):
            self.assertIn(f"Bash({command}:*)", deny)

    def test_a_planner_may_write_tickets_but_not_settings(self):
        deny = self.rules("planner")["permissions"]["deny"]
        self.assertNotIn(f"Edit(/{self.copy}/.tollgate/**)", deny)
        self.assertIn(f"Edit(/{self.copy}/.tollgate/settings.json)", deny)

    def test_a_reviewer_and_the_advisor_read_only(self):
        for role in ("reviewer", "advisor", "analyst"):
            p = self.rules(role)["permissions"]
            self.assertEqual(p["allow"], ["Read", "Grep", "Glob"])
            for tool in ("Edit", "Write", "Bash"):
                self.assertIn(tool, p["deny"])

    def test_a_builder_is_not_read_only(self):
        deny = self.rules("builder")["permissions"]["deny"]
        self.assertNotIn("Edit", deny)
        self.assertNotIn("Bash", deny)

    def test_the_sandbox_and_the_hook_are_on(self):
        rules = self.rules("builder")
        self.assertTrue(rules["sandbox"]["enabled"])
        self.assertFalse(rules["sandbox"]["allowUnsandboxedCommands"])
        command = rules["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertIn("--role builder", command)
        self.assertIn(str(self.copy), command)

    def test_an_unknown_role_has_no_settings(self):
        with self.assertRaises(ValueError):
            policy.settings_for("owner", str(self.copy), str(self.project))

    def test_the_file_is_written_outside_the_copy_only(self):
        out = state.path(str(self.project), "run", "T-1-builder.settings.json")
        policy.write("builder", str(self.copy), str(self.project), str(out))
        self.assertIn("permissions", json.loads(out.read_text()))
        with self.assertRaises(ValueError):
            policy.write("builder", str(self.copy), str(self.project), str(self.copy / "s.json"))


if __name__ == "__main__":
    unittest.main()
