"""Single steps of the task loop (driver/task.py), with a scripted role in place of the
subagents: the plan review and what goes to each role."""

import unittest
from pathlib import Path

from driver import roles
from driver.log import Log, read
from driver.task import Task
from gate import settings as st
from tests.driver_fakes import FakeStore, Sample
from tests.fake_role import PLAN, TICKET_T1, TICKET_T2

MINOR = {"level": "minor", "text": "the plan says greet is in main.py; it is in app.py"}
MAJOR = {"level": "major", "text": "drop demo-2?"}


class Script:
    """A role that answers from a script. reviews maps a lens to a list of findings for
    each round; fix(inputs) runs in the builder's answer step."""

    def __init__(self, reviews=None, fix=None):
        self.reviews = reviews or {}
        self.fix = fix
        self.calls = []
        self.rounds = {}

    def __call__(self, name, inputs, lens=None, command=None):
        self.calls.append((name, lens, inputs))
        if name == "reviewer":
            n = self.rounds[lens] = self.rounds.get(lens, 0) + 1
            found = self.reviews.get(lens, [])
            return roles.Answer({"verdict": "pass",
                                 "findings": found[n - 1] if n <= len(found) else []}, 0, 0)
        if name == "builder" and inputs.get("mode") == "answer":
            if self.fix:
                self.fix(inputs)
            return roles.Answer({"answers": [{"finding": i, "action": "fix", "evidence": "x"}
                                             for i, _ in enumerate(inputs["findings"])]}, 0, 0)
        raise AssertionError(f"unexpected role {name}")

    def answers(self):
        return [i for n, _, i in self.calls if n == "builder" and i.get("mode") == "answer"]


class TaskCase(unittest.TestCase):
    def setUp(self):
        self.s = Sample(ticket=False)
        self.addCleanup(self.s.close)
        p = self.s.project
        self.plan_file = Path(p, ".tollgate/plans/demo.md")
        self.plan_file.parent.mkdir(parents=True)
        self.plan_file.write_text(PLAN.format(task="demo", request="Add shout and whisper."))
        for tid, text in (("demo-1", TICKET_T1), ("demo-2", TICKET_T2)):
            Path(p, f".tollgate/tickets/{tid}").mkdir(parents=True)
            Path(p, f".tollgate/tickets/{tid}/ticket.md").write_text(text.format(task="demo"))
        self.task = Task(str(p), "demo", "Add shout and whisper.", FakeStore(p))
        self.task.copy = str(p)
        self.task.settings = st.load_from_ref(str(p), "main")
        self.task.log = Log(self.task.log_path, task="demo")
        self.addCleanup(self.task.log.close)

    def events(self, name=None):
        found = read(self.task.log_path)
        return [e for e in found if name is None or e["event"] == name]

    def fix_plan(self, inputs):
        self.plan_file.write_text(self.plan_file.read_text().replace(
            "## Design\n", "## Design\nThe code is in app.py.\n", 1))


class MinorFindingsTest(TaskCase):
    def test_a_clean_round_gives_its_minor_findings_to_the_builder(self):
        self.task.role = Script({"readiness": [[MINOR], [MINOR]]}, fix=self.fix_plan)
        self.assertEqual(self.task.review_plan(), [])
        self.assertEqual(self.task.role.answers()[0]["findings"], [dict(MINOR, lens="readiness")])
        # The builder changed the plan, so a second round reads it. Its minor finding,
        # the same one, makes it no less clean: no third answer step.
        self.assertEqual([e["round"] for e in self.events("plan_reviewed")], [1, 1, 1, 2, 2, 2])
        self.assertEqual(len(self.task.role.answers()), 1)
        self.assertEqual(self.events("plan_review_clean")[0]["round"], 2)

    def test_an_answer_that_changes_nothing_ends_the_review_clean(self):
        self.task.role = Script({"readiness": [[MINOR]]})
        self.assertEqual(self.task.review_plan(), [])
        self.assertEqual(len(self.task.role.answers()), 1)
        self.assertEqual(self.events("plan_review_clean")[0]["round"], 1)
        self.assertEqual(self.events("plan_answered")[0]["minor"], 1)

    def test_minor_findings_go_with_the_open_ones_and_cannot_be_escalated(self):
        self.task.role = Script({"simplicity": [[MAJOR, MINOR]]}, fix=self.fix_plan)
        self.assertEqual(self.task.review_plan(), [])
        first = self.task.role.answers()[0]["findings"]
        self.assertEqual(first, [dict(MAJOR, lens="simplicity"), dict(MINOR, lens="simplicity")])


if __name__ == "__main__":
    unittest.main()
