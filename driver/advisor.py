"""Ask a person through the store, and read the answer.

The driver writes one question in the state folder for each decision a person
makes. You answer it with the store, for example from the inbox skill:

    tollgate decide <decision> [a hint for the builder]

The store keeps the answer as {decision, hint, at}. The driver reads the answer
when it starts again, so a question never blocks other tickets.
"""

import json
import re

from gate import state
from gate.store import StoreError
from driver import history
from driver.log import read

DECIDE = re.compile(r"^(?:tollgate decide )?([a-z_]+)\b[ \t]*(.*)$")


class Waiting(Exception):
    """The question waits for a person."""


def parse_answer(answer) -> dict | None:
    """{decision, hint} from an answer: a structured answer, or the text
    `tollgate decide <decision> [hint]`. None when there is no decision."""
    if isinstance(answer, dict) and answer.get("decision"):
        return {"decision": str(answer["decision"]), "hint": str(answer.get("hint") or "")}
    text = answer.get("body", "") if isinstance(answer, dict) else answer
    if not isinstance(text, str):
        return None
    first = text.strip().splitlines()[:1]
    m = DECIDE.match(first[0].strip()) if first else None
    return {"decision": m.group(1), "hint": m.group(2).strip()} if m else None


def question(store, n: int) -> dict | None:
    """Question n, open or closed, or None."""
    if hasattr(store, "question"):
        return store.question(n)
    for name in (f"{n}.json", f"{n}.closed.json"):
        path = state.path(store.project, "questions", name)
        if path.exists():
            return json.loads(path.read_text())
    return None


def pending(log_path: str) -> dict | None:
    """The open question in this log, or None: {"question", "reason"}."""
    return history.open_question(read(log_path))


def ask_person(store, log, log_path: str, subject: str, reason: str, options: list) -> dict:
    """Return the person's decision, or raise Waiting after writing the question."""
    asked = history.open_question(read(log_path))
    if asked:
        n = asked["question"]
        found = question(store, n) or {}
        decision = parse_answer(found.get("answer"))
        if decision and decision["decision"] in options:
            try:
                store.close_question(n)
            except StoreError:
                pass  # a closed question stays closed
            log.add("advisor_decided", by="person", question=n, **decision)
            return decision
        log.add("still_waiting", question=n)
        raise Waiting(f"question {n} waits for a decision")
    body = (f"{reason}\n\nAnswer with one of:\n\n"
            + "\n".join(f"    tollgate decide {o} [hint]" for o in options))
    n = store.ask(f"tollgate: {subject} waits for a decision", body, options)
    log.add("waiting_for_advisor", by="person", question=n, reason=reason, options=options)
    raise Waiting(f"asked in question {n}")
