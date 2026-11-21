"""Stage 4 proof: home, submodules, sync, inbox, base suite, roadmap, and retro.

    python3 -m unittest tests.proof_stage4 -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gate import roadmap as rm
from gate import settings as st
from driver import retro
from driver.log import read
from setup import base_suite, home, inbox, sync_rules
from tests.fakes import Sample, driver_env, run_driver
from tests.helpers import sh

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


class FakeGh:
    def __init__(self, private=True, issues=None):
        self.private = private
        self.issues = issues or {}
        self.prs = []

    def get(self, path):
        if path.startswith("repos/") and "/issues" in path:
            return self.issues.get(path.split("/")[1] + "/" + path.split("/")[2], [])
        return {"private": self.private}

    def api(self, method, path, body=None):
        self.prs.append((path, body))
        return {"number": len(self.prs)}


def git_env():
    env = dict(os.environ)
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e")
    return env


class HomeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        os.environ.update({k: v for k, v in git_env().items() if k.startswith("GIT_")})

    def project(self, name, settings=True):
        bare = self.root / f"{name}.git"
        sh(self.root, "git", "init", "-q", "--bare", "-b", "main", str(bare))
        work = self.root / f"{name}-work"
        sh(self.root, "git", "clone", "-q", str(bare), str(work))
        (work / "README.md").write_text(name)
        if settings:
            (work / ".tollgate").mkdir()
            (work / ".tollgate/settings.json").write_text("{}")
        sh(work, "git", "add", "-A")
        sh(work, "git", "commit", "-q", "-m", "start")
        sh(work, "git", "push", "-q", "origin", "main")
        return bare

    def test_init_refuses_a_public_remote_and_a_folder_that_is_not_empty(self):
        h = self.root / "home"
        h.mkdir()
        with self.assertRaisesRegex(home.HomeError, "public"):
            home.init(str(h), "me/home", FakeGh(private=False))
        (h / "notes.txt").write_text("x")
        with self.assertRaisesRegex(home.HomeError, "not empty"):
            home.init(str(h))

    def test_add_projects_as_submodules_sync_rules_and_read_the_inbox(self):
        h = self.root / "home"
        h.mkdir()
        self.assertEqual(home.init(str(h), "me/home", FakeGh()), "created")
        a, b = self.project("billing"), self.project("search", settings=False)
        first = home.add(str(h), "org/billing", url=str(a))
        self.assertEqual((first["added"], first["has_settings"]), (True, True))
        self.assertFalse(home.add(str(h), "org/search", url=str(b))["has_settings"])
        self.assertFalse(home.add(str(h), "org/billing", url=str(a))["added"])
        modules = (h / ".gitmodules").read_text()
        self.assertIn("projects/billing", modules)
        self.assertIn("projects/search", modules)

        (h / "rules/lenses/naming.md").write_text("# Lens: naming\nNames are plain words.\n")
        gh = FakeGh()
        results = sync_rules.sync(str(h), gh)
        self.assertEqual([r["result"] for r in results], ["pull request #1", "pull request #2"])
        self.assertEqual(gh.prs[0][0], "repos/org/billing/pulls")
        synced = sh(self.root, "git", "--git-dir", str(a), "show",
                    "tollgate-sync:.tollgate/lenses/naming.md")
        self.assertIn("Names are plain words.", synced)
        # Once billing merges its pull request, it is in sync. Search is not yet.
        sh(self.root, "git", "--git-dir", str(a), "update-ref", "refs/heads/main",
           "refs/heads/tollgate-sync")
        self.assertEqual([r["result"] for r in sync_rules.sync(str(h), gh, push=False)],
                         ["already in sync", "committed, not pushed"])

        waiting = FakeGh(issues={"org/search": [
            {"number": 4, "title": "tollgate: ticket T-9 waits for a decision"}]})
        found = inbox.inbox([p["name"] for p in home.load(str(h))["projects"]], waiting)
        self.assertEqual([(f["repo"], f["issue"]) for f in found], [("org/search", 4)])


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
        sample = Sample(builder="pass1",
                        advisor=(f"{sys.executable} {Path(__file__).parent / 'fake_role.py'} ok",),
                        extra={"base": base})
        self.addCleanup(sample.close)
        p = sample.project
        Path(p, rm.roadmap_path("orders")).parent.mkdir(parents=True)
        Path(p, rm.roadmap_path("orders")).write_text(roadmap)
        Path(p, ".tollgate/tickets/orders-done").mkdir(parents=True)
        Path(p, ".tollgate/tickets/orders-done/ticket.md").write_text(CHECKLIST)
        code = ("import sys; from driver.roadmap import main; from tests.fakes import LocalServer; "
                "from pathlib import Path; "
                f"sys.exit(main(['--project', {str(p)!r}, '--roadmap', 'orders'], "
                f"server=LocalServer(Path({str(sample.bare)!r}))))")
        env = driver_env(sample)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        result = subprocess.run([sys.executable, "-c", code], cwd=env["PYTHONPATH"], env=env,
                                capture_output=True, text=True, timeout=600, check=False)
        events = read(str(p / ".tollgate/logs/roadmap-orders.jsonl"))
        return sample, result, events

    def test_a_roadmap_freezes_its_checklist_first_runs_each_task_then_checks_the_whole(self):
        sample, result, events = self.run_roadmap({name: "true" for name in base_suite.NAMES})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e["event"] for e in events],
                         ["checklist_frozen", "task_done", "base_passed", "task_done",
                          "roadmap_done"])
        tags = sh(sample.bare, "git", "tag").split()
        for tag in ("tg/freeze/orders-done/1", "tg/plan/orders-base/1", "tg/plan/orders-more/1"):
            self.assertIn(tag, tags)

    def test_a_roadmap_with_only_a_base_checks_it_after_the_last_task(self):
        only_base = ROADMAP.replace("- orders-more: Add shout and whisper again, as a second task.\n",
                                    "")
        _, result, events = self.run_roadmap({name: "true" for name in base_suite.NAMES},
                                             only_base)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([e["event"] for e in events],
                         ["checklist_frozen", "task_done", "base_passed", "roadmap_done"])

    def test_a_base_with_a_gap_stops_the_roadmap_before_the_skeleton(self):
        base = {name: "true" for name in base_suite.NAMES}
        base["one_log_line"] = ""
        sample, result, events = self.run_roadmap(base)
        self.assertEqual(result.returncode, 1)
        self.assertEqual([e["event"] for e in events],
                         ["checklist_frozen", "task_done", "roadmap_waiting"])
        self.assertIn("one_log_line (not set)", events[-1]["reason"])
        self.assertNotIn("tg/plan/orders-more/1", sh(sample.bare, "git", "tag").split())


class BaseCheckTest(unittest.TestCase):
    def test_a_base_suite_that_cannot_start_stops_the_roadmap_with_a_reason(self):
        from unittest import mock

        from driver import roadmap as dr
        from driver.log import Log
        with tempfile.TemporaryDirectory() as d:
            log_path = os.path.join(d, "roadmap.jsonl")
            with mock.patch.object(dr.st, "load_from_ref", return_value={"base": {}}), \
                    mock.patch.object(dr.base_suite, "run", side_effect=OSError("no folder")), \
                    Log(log_path, roadmap="r") as log:
                self.assertEqual(dr.check_base(d, log), 1)
            self.assertIn("could not run: no folder", read(log_path)[-1]["reason"])

    def test_settings_that_cannot_be_read_stop_the_roadmap_with_a_reason(self):
        from driver import roadmap as dr
        from driver.log import Log
        with tempfile.TemporaryDirectory() as d:
            sh(d, "git", "init", "-q")
            log_path = os.path.join(d, "roadmap.jsonl")
            with Log(log_path, roadmap="r") as log:
                self.assertEqual(dr.check_base(d, log), 1)
            last = read(log_path)[-1]
            self.assertEqual(last["event"], "roadmap_waiting")
            self.assertIn("cannot read the settings", last["reason"])


class RetroTest(unittest.TestCase):
    def test_numbers_and_candidates(self):
        sample = Sample(builder="pass2")
        self.addCleanup(sample.close)
        self.assertEqual(run_driver(sample).returncode, 0)
        nums, tickets = retro.numbers(str(sample.project), "demo")
        self.assertEqual(nums["tickets"], 1)
        self.assertEqual(nums["first_attempt_pass_pct"], 0)
        self.assertEqual(nums["mean_attempts"], 2)
        cands = retro.candidates(tickets)
        self.assertEqual([(c["ticket"], c["kind"]) for c in cands], [("T-1", "test")])
        text = Path(retro.write(str(sample.project), "demo")).read_text()
        self.assertIn("| mean attempts | 2.0 |", text)


if __name__ == "__main__":
    unittest.main()
