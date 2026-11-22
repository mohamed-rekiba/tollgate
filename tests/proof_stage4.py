"""Stage 4 proof: a roadmap, a home, the inbox, the base suite, and the retro, with
the real store.

    python3 -m unittest tests.proof_stage4 -v

Every step runs the command a skill names, as its own process.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from driver import retro
from gate import roadmap as rm
from gate import settings as st
from gate import state
from gate.store import Store
from setup import base_suite
from tests.proof_common import ROLE, Project, events

ROADMAP = """---
id: orders
checklist: orders-done
---
## Request
Greet people loudly and softly.

## Base
- orders-base: Add shout and whisper.

## Skeleton

## Features
- orders-more: Add shout and whisper again, as a second task.

## Not yet specified
A screen.
"""

CHECKLIST = """---
id: orders-done
plan: orders
seams: app.shout
tests: tests/test_t1.py
---
## Current behavior
There is no shout.

## Desired behavior
The whole request works.

## Checklist
- [C1, must] shout("ann") returns "HELLO ANN".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] shout has a docstring.

## Out of scope
A screen.
"""

ALL_SET = {name: "true" for name in base_suite.NAMES}


class RoadmapTest(unittest.TestCase):
    def test_the_format(self):
        r = rm.parse(ROADMAP)
        self.assertEqual([t[1] for t in r.tasks], ["orders-base", "orders-more"])
        self.assertEqual(r.checklist, "orders-done")
        with self.assertRaisesRegex(rm.RoadmapError, "appears twice"):
            rm.parse(ROADMAP.replace("orders-more:", "orders-base:"))
        with self.assertRaisesRegex(rm.RoadmapError, "no section: Skeleton"):
            rm.parse(ROADMAP.replace("## Skeleton\n", ""))

    def run_roadmap(self, base, roadmap=ROADMAP):
        p = Project(ticket=False, builder="pass1", advisor=(f"{ROLE} ok",), base=base)
        self.addCleanup(p.close)
        Path(p.project, rm.roadmap_path("orders")).parent.mkdir(parents=True)
        Path(p.project, rm.roadmap_path("orders")).write_text(roadmap)
        Path(p.project, ".tollgate/tickets/orders-done").mkdir(parents=True)
        Path(p.project, ".tollgate/tickets/orders-done/ticket.md").write_text(CHECKLIST)
        result = p.run("driver.roadmap", "--project", ".", "--roadmap", "orders")
        return p, result, p.log_of("roadmap-orders")

    def test_a_roadmap_locks_its_checklist_first_runs_each_task_then_checks_the_whole(self):
        p, result, log = self.run_roadmap(ALL_SET)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events(log), ["checklist_frozen", "task_done", "base_passed",
                                       "task_done", "roadmap_done"])
        self.assertEqual(p.lock("orders-done")["number"], 1)
        for task in ("orders-base", "orders-more"):
            self.assertTrue(state.path(str(p.project), "plans", f"{task}.json").exists(), task)
        self.assertEqual(events(p.log_of("orders-done"))[-1], "waiting_for_merge")
        status = p.run("driver.report", "--project", ".")
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Done", status.stdout)

    def test_a_roadmap_with_only_a_base_checks_it_after_the_last_task(self):
        only_base = ROADMAP.replace("- orders-more: Add shout and whisper again, as a second "
                                    "task.\n", "")
        _, result, log = self.run_roadmap(ALL_SET, only_base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events(log), ["checklist_frozen", "task_done", "base_passed",
                                       "roadmap_done"])

    def test_a_base_with_a_gap_stops_the_roadmap_before_the_skeleton(self):
        p, result, log = self.run_roadmap({**ALL_SET, "one_log_line": ""})
        self.assertEqual(result.returncode, 1)
        self.assertEqual(events(log), ["checklist_frozen", "task_done", "roadmap_waiting"])
        self.assertIn("one_log_line (not set)", log[-1]["reason"])
        self.assertFalse(state.path(str(p.project), "plans", "orders-more.json").exists())


class BaseSuiteTest(unittest.TestCase):
    def test_five_commands_and_a_gap_for_each_one_not_set(self):
        s = st.parse(json.dumps({"base": {"checks_run": "true", "parallel_tests": "true",
                                          "env_up_down": "exit 3", "one_log_line": "true"}}))
        with tempfile.TemporaryDirectory() as d:
            results = {r["name"]: r for r in base_suite.run(s, d)}
        self.assertEqual(list(results), list(base_suite.NAMES))
        self.assertTrue(results["checks_run"]["passed"])
        self.assertIn("ended with 3", results["env_up_down"]["why"])
        self.assertEqual(results["bad_setting_stops"]["why"], "not set")


class HomeTest(unittest.TestCase):
    """A home with one Tollgate project, as the home and inbox skills run it."""

    def setUp(self):
        self.p = Project(ticket=False)
        self.addCleanup(self.p.close)
        self.home = self.p.root / "home"
        self.home.mkdir()

    def run_in(self, folder, module, *args) -> subprocess.CompletedProcess:
        return self.p.run(module, *args, cwd=folder)

    def test_create_add_list_and_sync_then_you_approve_and_merge_the_rules(self):
        h = self.home
        self.assertEqual(self.run_in(h, "setup.home", "init").stdout.strip(), "created")
        added = self.run_in(h, "setup.home", "add", str(self.p.project), "--name", "billing")
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertEqual(json.loads(added.stdout)["has_settings"], True)
        self.assertIn("billing\tprojects/billing", self.run_in(h, "setup.home", "list").stdout)
        (h / "rules/lenses/naming.md").write_text("# Lens: naming\nNames are plain words.\n")
        synced = self.run_in(h, "setup.sync_rules")
        self.assertEqual(synced.returncode, 0, synced.stderr)
        self.assertIn("tollgate-sync", json.loads(synced.stdout.splitlines()[0])["result"])
        project = h / "projects/billing"
        # A change made by hand: it has no pass record, so only your approval merges it.
        self.assertIn("a change made by hand",
                      self.run_in(project, "setup.merge", "show", "tollgate-sync").stdout)
        refused = self.run_in(project, "setup.merge", "merge", "tollgate-sync")
        self.assertEqual(refused.returncode, 1)
        approved = self.run_in(project, "setup.merge", "approve", "tollgate-sync",
                               "--key", str(self.p.owner))
        self.assertEqual(approved.returncode, 0, approved.stderr)
        merged = self.run_in(project, "setup.merge", "merge", "tollgate-sync")
        self.assertEqual(merged.returncode, 0, merged.stderr)
        self.assertEqual((project / ".tollgate/lenses/naming.md").read_text(),
                         "# Lens: naming\nNames are plain words.\n")
        again = self.run_in(h, "setup.sync_rules")
        self.assertEqual(json.loads(again.stdout.splitlines()[0])["result"], "already in sync")

    def test_the_inbox_lists_questions_across_the_home_and_records_your_answer(self):
        h = self.home
        self.run_in(h, "setup.home", "init")
        self.run_in(h, "setup.home", "add", str(self.p.project), "--name", "billing")
        project = h / "projects/billing"
        n = Store(str(project)).ask("tollgate: ticket T-9 waits for a decision", "why",
                                    ["retry", "park"])
        found = self.run_in(h, "setup.inbox")
        self.assertIn(f"question {n}: tollgate: ticket T-9 waits for a decision", found.stdout)
        self.assertIn("options: retry, park", found.stdout)
        wrong = self.run_in(h, "setup.inbox", "--project", "projects/billing", "answer", str(n),
                            "merge")
        self.assertEqual(wrong.returncode, 1)
        answered = self.run_in(h, "setup.inbox", "--project", "projects/billing", "answer",
                               str(n), "retry", "look", "at", "the", "log")
        self.assertEqual(answered.returncode, 0, answered.stderr)
        self.assertEqual(Store(str(project)).question(n)["answer"]["hint"], "look at the log")
        self.assertIn("Nothing waits for you.", self.run_in(h, "setup.inbox").stdout)

    def test_a_folder_that_is_not_empty_is_not_made_a_home(self):
        (self.home / "notes.txt").write_text("x")
        refused = self.run_in(self.home, "setup.home", "init")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("not empty", refused.stderr)


class RetroTest(unittest.TestCase):
    def test_numbers_and_candidates_in_the_state_folder(self):
        p = Project(builder="pass2")
        self.addCleanup(p.close)
        self.assertEqual(p.drive().returncode, 0)
        nums, tickets = retro.numbers(str(p.project), "demo")
        self.assertEqual((nums["tickets"], nums["first_attempt_pass_pct"], nums["mean_attempts"]),
                         (1, 0, 2))
        self.assertEqual([(c["ticket"], c["kind"]) for c in retro.candidates(tickets)],
                         [("T-1", "test")])
        done = p.run("driver.retro", "--project", ".", "--task", "demo")
        self.assertEqual(done.returncode, 0, done.stderr)
        path = Path(done.stdout.strip())
        self.assertEqual(path, state.path(str(p.project), "lessons", "demo.md"))
        self.assertIn("| mean attempts | 2.0 |", path.read_text())


if __name__ == "__main__":
    unittest.main()
