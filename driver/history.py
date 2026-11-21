"""What a log says. Each event in a log means one thing, and this module is the
one place that says what. The driver resumes from it; the report, the retro,
and the advisor read it. The log itself is written by driver/log.py.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

# The state of a ticket, as a person reads it, from the last event that sets one.
STATES = {
    "merged": "merged", "waiting_for_merge": "pull request open", "pr_opened": "pull request open",
    "parked": "parked", "waiting_for_advisor": "waits for a person", "still_waiting":
    "waits for a person", "stopped": "stopped", "attempt_passed": "building",
    "attempt_failed": "building", "attempt_started": "building", "frozen": "frozen",
    "tests_reviewed": "tests written", "tests_written": "tests written", "started": "started",
}
ATTEMPT_ENDS = ("attempt_failed", "attempt_passed")
REASONS = ("parked", "waiting_for_advisor", "stopped")


@dataclass
class Ticket:
    """A ticket as its log tells it. The driver changes it as it works, then logs the change."""
    ticket: str = ""
    task: str = ""
    state: str = "not started"
    tests_done: bool = False
    frozen: str = ""
    rejections: int = 0
    attempts: int = 0
    best_commit: str = ""
    best_score: int = -1
    last_failed: tuple = ()
    passed_commit: str = ""
    tier: int | None = None
    pr: int = 0
    reason: str = ""
    extra_attempts: int = 0
    ai_decisions: int = 0
    hint: str = ""
    stronger: bool = False


def replay(events: list) -> Ticket:
    """Read the events of one ticket in order, and return where the ticket stands."""
    t = Ticket(ticket=events[0].get("ticket", "") if events else "",
               task=events[0].get("task", "") if events else "")
    for e in events:
        kind = e["event"]
        t.state = STATES.get(kind, t.state)
        if kind in REASONS:
            t.reason = e.get("reason", "")
        if kind == "tests_reviewed":
            t.tests_done = True
        elif kind == "tests_rejected":
            t.rejections += 1
        elif kind == "frozen":
            t.frozen = e.get("tag", "")
            t.best_commit = t.best_commit or e.get("commit", "")
        elif kind in ATTEMPT_ENDS:
            t.attempts = e.get("attempt", t.attempts + 1)
            t.last_failed = tuple(map(tuple, e.get("failed_key", [[], []])))
            t.tier = e.get("tier", t.tier)
            if e.get("score", -1) > t.best_score:
                t.best_score, t.best_commit = e["score"], e.get("commit", t.best_commit)
            if kind == "attempt_passed":
                t.passed_commit = e.get("commit", "")
        elif kind == "pr_opened":
            t.pr = e.get("pr", 0)
        elif kind == "advisor_decided":
            t.ai_decisions += 1 if e.get("by") == "ai" else 0
            if e.get("decision") in ("retry", "stronger"):
                t.extra_attempts += 1
                t.hint = e.get("hint", "")
                t.stronger = t.stronger or e.get("decision") == "stronger"
    return t


def open_question(events: list) -> dict | None:
    """The question a person has not answered yet, or None: {"issue", "reason"}."""
    answered = {e.get("issue") for e in events
                if e["event"] == "advisor_decided" and e.get("by") == "person"}
    for e in reversed(events):
        if e["event"] == "waiting_for_advisor" and e.get("issue"):
            return None if e["issue"] in answered else {"issue": e["issue"],
                                                        "reason": e.get("reason", "")}
    return None


def cost(events: list) -> float:
    """What the AI sessions in these events cost, in USD."""
    return round(sum(float(e.get("cost_usd") or 0) for e in events), 4)


def minutes(events: list) -> int:
    """Minutes from the first event to the last."""
    stamps = [datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
              for e in events if "at" in e]
    return round((max(stamps) - min(stamps)).total_seconds() / 60) if stamps else 0
