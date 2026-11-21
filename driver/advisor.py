"""Ask a person on the server, and read the answer.

The driver opens one issue with the label tg-waiting for each open question. A
person answers with a comment whose first line is

    tollgate decide <decision> [a hint for the builder]

Only a user named under `approvers` in the settings counts. The driver reads the
answer when it starts again, so a question never blocks other tickets.
"""

import re

from driver.log import read

DECIDE = re.compile(r"^tollgate decide ([a-z_]+)\b[ \t]*(.*)$")
WAITING_LABEL = "tg-waiting"


class Waiting(Exception):
    """The question is open on the server."""


def first_decision(comments: list, approvers: list) -> dict | None:
    """comments: [{"user", "user_type", "body"}] oldest first. The newest valid answer wins."""
    for c in reversed(comments):
        if c.get("user_type") != "User" or c.get("user") not in approvers:
            continue
        first = (c.get("body") or "").strip().splitlines()[:1]
        m = DECIDE.match(first[0].strip()) if first else None
        if m:
            return {"decision": m.group(1), "hint": m.group(2).strip(), "by": c["user"]}
    return None


def pending(log_path: str) -> dict | None:
    """The open question in this log, or None: {"issue", "reason"}."""
    events = read(log_path)
    answered = {e.get("issue") for e in events
                if e["event"] == "advisor_decided" and e.get("by") == "person"}
    for e in reversed(events):
        if e["event"] == "waiting_for_advisor" and e.get("issue"):
            return None if e["issue"] in answered else {"issue": e["issue"], "reason": e["reason"]}
    return None


def ask_person(server, log, log_path: str, subject: str, reason: str, options: list,
               approvers: list) -> dict:
    """Return the person's decision, or raise Waiting after opening the question."""
    events = read(log_path)
    asked = [e for e in events if e["event"] == "waiting_for_advisor" and e.get("issue")]
    answered = {e.get("issue") for e in events
                if e["event"] == "advisor_decided" and e.get("by") == "person"}
    open_issue = next((e["issue"] for e in reversed(asked) if e["issue"] not in answered), None)
    if open_issue:
        found = first_decision(server.issue_comments(open_issue), approvers)
        if found and found["decision"] in options:
            server.close_question(open_issue)
            log.add("advisor_decided", by="person", issue=open_issue, decision=found["decision"],
                    hint=found["hint"], person=found["by"])
            return found
        log.add("still_waiting", issue=open_issue)
        raise Waiting(f"issue {open_issue} waits for a decision")
    body = (f"{reason}\n\nAnswer with a comment whose first line is one of:\n\n"
            + "\n".join(f"    tollgate decide {o} [hint]" for o in options)
            + "\n\nOnly a user named under `approvers` in the settings counts.")
    issue = server.ask(f"tollgate: {subject} waits for a decision", body)
    log.add("waiting_for_advisor", by="person", issue=issue, reason=reason, options=options)
    raise Waiting(f"asked in issue {issue}")
