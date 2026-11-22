"""Tests for settings, paths, tickets, JUnit reports, manifests, tiers, and checks."""

import json
import tempfile
import unittest
from pathlib import Path

from gate import checks, junit, manifest, paths, settings, tickets, tiers
from tests.helpers import TICKET, Repo, settings_text
from tests.helpers import junit as make_junit


class PathsTest(unittest.TestCase):
    def test_double_star_matches_any_depth(self):
        self.assertTrue(paths.matches("src/auth/a/b.py", ["src/auth/**"]))
        self.assertTrue(paths.matches("conftest.py", ["**/conftest.py"]))
        self.assertTrue(paths.matches("a/b/conftest.py", ["**/conftest.py"]))

    def test_single_star_stays_in_one_folder(self):
        self.assertFalse(paths.matches("src/a/b.py", ["src/*.py"]))
        self.assertTrue(paths.matches("src/b.py", ["src/*.py"]))


class SettingsTest(unittest.TestCase):
    def test_unknown_key_is_named(self):
        with self.assertRaisesRegex(settings.SettingsError, "unknown key: stop.retries"):
            settings.parse('{"stop": {"retries": 2}}')

    def test_check_needs_a_run_command(self):
        with self.assertRaisesRegex(settings.SettingsError, "checks.tests needs a run"):
            settings.parse('{"checks": {"tests": {"report": "x.xml"}}}')

    def test_isolation_is_container_or_sandbox(self):
        self.assertEqual(settings.parse('{"isolation": "sandbox"}')["isolation"], "sandbox")
        with self.assertRaisesRegex(settings.SettingsError, "isolation must be"):
            settings.parse('{"isolation": "none"}')

    def test_each_signer_is_a_public_key_line(self):
        import base64
        blob = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519" + b"\x00" * 36).decode()
        good = f"ssh-ed25519 {blob} me@laptop"
        self.assertEqual(settings.parse(json.dumps({"signers": [good]}))["signers"], [good])
        wrong_type = f"ssh-rsa {blob}"
        for bad in ("ssh-ed25519", "not a key", wrong_type, f"ssh-ed25519 {blob}!", 7):
            with self.assertRaisesRegex(settings.SettingsError, "not an SSH public key"):
                settings.parse(json.dumps({"signers": [bad]}))

    def test_checkpoints_default_to_the_plan_and_the_task(self):
        self.assertEqual(settings.parse("{}")["checkpoints"], ["plan", "task"])
        self.assertEqual(settings.parse('{"checkpoints": ["plan", "ticket", "task"]}')["checkpoints"],
                         ["plan", "ticket", "task"])
        self.assertEqual(settings.parse('{"checkpoints": []}')["checkpoints"], [])

    def test_an_unknown_checkpoint_is_refused(self):
        for bad in ('["plan", "tikcet"]', '"plan"', '[1]'):
            with self.subTest(bad=bad), self.assertRaisesRegex(settings.SettingsError, "checkpoints"):
                settings.parse(f'{{"checkpoints": {bad}}}')

    def test_an_unknown_key_is_refused(self):
        for key in ("action", "version", "approvers", "sandbox"):
            with self.assertRaisesRegex(settings.SettingsError, f"unknown key: {key}"):
                settings.parse(json.dumps({key: ""}))

    def test_built_in_harness_cannot_be_removed(self):
        s = settings.parse('{"harness": []}')
        self.assertIn(".github/**", s["harness"])
        self.assertIn("**/conftest.py", s["harness"])

    def test_reads_from_the_main_branch_not_the_working_folder(self):
        repo = Repo()
        self.addCleanup(repo.close)
        repo.write(settings.PATH, '{"pass_score": 70}')
        repo.commit()
        repo.write(settings.PATH, '{"pass_score": 1}')
        self.assertEqual(settings.load_from_ref(str(repo.path), "main")["pass_score"], 70)


class TicketsTest(unittest.TestCase):
    def test_reads_items_and_marks(self):
        t = tickets.parse(TICKET)
        self.assertEqual(t.id, "T-1")
        self.assertEqual([i.id for i in t.items], ["C1", "C2", "C3"])
        self.assertTrue(t.item("C2").keeps_behavior)
        self.assertFalse(t.item("C3").must)
        self.assertEqual(t.tests, ["tests/test_t1.py"])

    def test_needs_three_items(self):
        short = TICKET.replace("- [C3] The wait between tries is written to the log.\n", "")
        with self.assertRaisesRegex(tickets.TicketError, "3 to 7 items"):
            tickets.parse(short)

    def test_needs_a_must_have_item(self):
        text = TICKET.replace("C1, must", "C1").replace("C2, must, keeps behavior", "C2")
        with self.assertRaisesRegex(tickets.TicketError, "at least one must-have"):
            tickets.parse(text)

    def test_keeps_behavior_must_be_must(self):
        text = TICKET.replace("C2, must, keeps behavior", "C2, keeps behavior")
        with self.assertRaisesRegex(tickets.TicketError, "must be a must-have"):
            tickets.parse(text)

    def test_item_of_test(self):
        self.assertEqual(tickets.item_of_test("tests.test_t1::test_c12_works"), "C12")
        self.assertIsNone(tickets.item_of_test("tests.test_t1::test_works"))


class JunitTest(unittest.TestCase):
    def test_statuses_and_files(self):
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
            f.write(make_junit({"tests.test_t1::test_a": "passed",
                                "tests.test_t1::test_b": "failed",
                                "tests.test_t1::test_c": "skipped"}))
        found = junit.read(f.name)
        Path(f.name).unlink()
        self.assertEqual(found["tests.test_t1::test_b"].status, "failed")
        self.assertEqual(found["tests.test_t1::test_c"].status, "skipped")
        self.assertTrue(junit.in_files(found["tests.test_t1::test_a"], ["tests/test_t1.py"]))
        self.assertFalse(junit.in_files(found["tests.test_t1::test_a"], ["tests/test_t2.py"]))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.repo = Repo()
        self.addCleanup(self.repo.close)
        self.repo.write(manifest.ticket_path("T-1"), TICKET)
        self.repo.write("tests/test_t1.py", "# tests\n")
        self.commit = self.repo.commit()
        self.ticket = tickets.parse(TICKET)

    def results(self, **status):
        default = {"test_c1_retries": "failed", "test_c2_sent_once": "passed",
                   "test_c3_wait_logged": "failed"}
        default.update(status)
        return {f"tests.test_t1::{n}": junit.TestResult(f"tests.test_t1::{n}", s, "")
                for n, s in default.items()}

    def test_builds_a_manifest(self):
        m = manifest.build(str(self.repo.path), self.commit, self.ticket, self.results())
        self.assertEqual(m["commit"], self.commit)
        self.assertEqual(len(m["tests"]), 3)
        self.assertEqual(m["keeps_behavior"], ["tests.test_t1::test_c2_sent_once"])

    def test_refuses_a_new_test_that_already_passes(self):
        with self.assertRaisesRegex(manifest.FreezeError, "passed before the build"):
            manifest.build(str(self.repo.path), self.commit, self.ticket,
                           self.results(test_c1_retries="passed"))

    def test_refuses_a_must_have_item_with_no_test(self):
        r = self.results()
        del r["tests.test_t1::test_c1_retries"]
        with self.assertRaisesRegex(manifest.FreezeError, "no test: C1"):
            manifest.build(str(self.repo.path), self.commit, self.ticket, r)

    def test_refuses_a_skipped_test(self):
        with self.assertRaisesRegex(manifest.FreezeError, "was skipped"):
            manifest.build(str(self.repo.path), self.commit, self.ticket,
                           self.results(test_c3_wait_logged="skipped"))

    def test_reports_a_changed_frozen_file(self):
        m = manifest.build(str(self.repo.path), self.commit, self.ticket, self.results())
        self.repo.write("tests/test_t1.py", "# weakened\n")
        head = self.repo.commit()
        self.assertEqual(manifest.changed(m, str(self.repo.path), head), ["tests/test_t1.py"])


class TiersTest(unittest.TestCase):
    def setUp(self):
        self.s = settings.parse('{"tiers": {"3": ["src/auth/**"], "4": ["migrations/**"]}}')

    def test_small_change_is_tier_1(self):
        self.assertEqual(tiers.tier(self.s, {"a.py": 20, "b.py": 10})[0], 1)

    def test_large_change_is_tier_2(self):
        self.assertEqual(tiers.tier(self.s, {"a.py": 60})[0], 2)

    def test_path_rules(self):
        self.assertEqual(tiers.tier(self.s, {"src/auth/login.py": 1})[0], 3)
        self.assertEqual(tiers.tier(self.s, {"migrations/0001.sql": 1})[0], 4)
        self.assertEqual(tiers.tier(self.s, {"pytest.ini": 1})[0], 4)

    def test_frozen_files_do_not_count(self):
        self.assertEqual(tiers.tier(self.s, {"src/a.py": 5, "tests/test_t1.py": 500},
                                    frozen={"tests/test_t1.py"})[0], 1)


class ChecksTest(unittest.TestCase):
    def test_runs_checks_and_reads_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "r.xml").write_text(make_junit({"t::test_c1_a": "passed"}))
            s = settings.parse(settings_text(checks={
                "tests": {"run": "cp r.xml report.xml", "report": "report.xml"},
                "style": {"run": "exit 3"}}))
            r = checks.run(s, d)
        self.assertEqual(r.failed_checks(), ["style"])
        self.assertEqual(r.tests["t::test_c1_a"]["status"], "passed")
        self.assertEqual(checks.Results.from_json(r.to_json()).tests, r.tests)

    def test_project_commands_do_not_see_tollgates_import_path(self):
        import os
        os.environ["PYTHONPATH"] = "/tollgate/code"
        self.addCleanup(os.environ.pop, "PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as d:
            s = settings.parse('{"checks": {"env": {"run": "test -z \\"$PYTHONPATH\\""}}}')
            self.assertEqual(checks.run(s, d).failed_checks(), [])

    def test_project_commands_see_no_token(self):
        import os
        for name in ("GH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
            os.environ[name] = "secret"
            self.addCleanup(os.environ.pop, name, None)
        with tempfile.TemporaryDirectory() as d:
            s = settings.parse(json.dumps({"checks": {"env": {
                "run": 'test -z "$GH_TOKEN" && test -z "$CLAUDE_CODE_OAUTH_TOKEN"'}}}))
            self.assertEqual(checks.run(s, d).failed_checks(), [])

    def test_a_check_past_its_time_limit_fails(self):
        with tempfile.TemporaryDirectory() as d:
            s = settings.parse('{"checks": {"slow": {"run": "sleep 5", "minutes": 0.01}}}')
            r = checks.run(s, d)
        self.assertTrue(r.checks[0].timed_out)
        self.assertFalse(r.checks[0].passed)


if __name__ == "__main__":
    unittest.main()
