"""A fake role for the driver's tests. It follows the role contract with no model.

    python3 tests/fake_role.py <mode> [<option>=<value> ...]

It reads the prompt on standard input, acts as the role named in its first line,
and prints {"result": ..., "total_cost_usd": ...}.

Builder modes: pass2 (fails attempt 1, passes attempt 2), same (fails the same
way every time), different (fails a different test each attempt), slow (runs too
long), github (also changes a file under .github).
Reviewer options: badline (names a line that does not exist).
Options: cost=<usd>, die_once=<path> (kill the driver once, on attempt 1).
"""

import json
import os
import re
import signal
import sys
import time
from pathlib import Path

GREET = 'def greet(name):\n    return f"hello {name}"\n'
SHOUT_OK = '\n\ndef shout(name):\n    """Return the greeting in capitals."""\n    return greet(name).upper()\n'
SHOUT_BAD = '\n\ndef shout(name):\n    """Return the greeting in capitals."""\n    return greet(name)\n'
WHISPER = '\n\ndef whisper(name):\n    """Return the greeting in small letters."""\n    return greet(name).lower()\n'
GREET_BROKEN = 'def greet(name):\n    return f"hi {name}"\n'
TESTS = '''import unittest

import app


class T(unittest.TestCase):
    def test_c1_shout(self):
        self.assertEqual(app.shout("ann"), "HELLO ANN")

    def test_c2_greet_kept(self):
        self.assertEqual(app.greet("ann"), "hello ann")
'''


TESTS_T2 = '''import unittest

import app


class T(unittest.TestCase):
    def test_c1_whisper(self):
        self.assertEqual(app.whisper("ANN"), "hello ann")

    def test_c2_greet_kept(self):
        self.assertEqual(app.greet("ann"), "hello ann")
'''

PLAN = """---
id: {task}
tickets: {task}-1, {task}-2
---
## Task
{request}

## Design
Add two functions next to greet.

## Files
app.py

## Seams
app.shout, app.whisper

## Tickets
- {task}-1: shout returns the greeting in capitals.
- {task}-2: whisper returns the greeting in small letters.
"""

TICKET_T1 = """---
id: {task}-1
plan: {task}
seams: app.shout
tests: tests/test_t1.py
---
## Current behavior
There is no shout.

## Desired behavior
shout returns the greeting in capitals.

## Checklist
- [C1, must] shout("ann") returns "HELLO ANN".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] shout has a docstring.

## Out of scope
Other languages.
"""

TICKET_T2 = """---
id: {task}-2
plan: {task}
seams: app.whisper
tests: tests/test_t2.py
---
## Current behavior
There is no whisper.

## Desired behavior
whisper returns the greeting in small letters.

## Checklist
- [C1, must] whisper("ANN") returns "hello ann".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] whisper has a docstring.

## Out of scope
Other languages.
"""


def count_marker(name: str) -> int:
    """Count calls across processes with a file in the working folder."""
    path = Path(name)
    n = int(path.read_text()) + 1 if path.exists() else 1
    path.write_text(str(n))
    return n


def inputs(prompt: str) -> dict:
    return json.loads(re.findall(r"```json\s*\n(.*?)\n```", prompt, re.DOTALL)[-1])


def answer(data: dict, cost: float) -> None:
    print(json.dumps({"result": "Done.\n\n```json\n" + json.dumps(data) + "\n```",
                      "total_cost_usd": cost}))


def main() -> int:
    mode = sys.argv[1]
    opts = dict(a.split("=", 1) for a in sys.argv[2:] if "=" in a)
    cost = float(opts.get("cost", 0.1))
    prompt = sys.stdin.read()
    first = prompt.splitlines()[0]
    data = inputs(prompt)
    if first == "# Role: test writer":
        Path("tests").mkdir(exist_ok=True)
        if data.get("ticket_id", "").endswith("-2"):
            Path("tests/test_t2.py").write_text(TESTS_T2)
            answer({"tests": [{"item": "C1", "file": "tests/test_t2.py", "name": "test_c1_whisper"},
                              {"item": "C2", "file": "tests/test_t2.py",
                               "name": "test_c2_greet_kept"}]}, cost)
            return 0
        bad = opts.get("tw_bad") and not data.get("rejected")
        Path("tests/test_t1.py").write_text(TESTS + ("# BADSTYLE\n" if bad else ""))
        answer({"tests": [{"item": "C1", "file": "tests/test_t1.py", "name": "test_c1_shout"},
                          {"item": "C2", "file": "tests/test_t1.py", "name": "test_c2_greet_kept"}]},
               cost)
    elif first == "# Role: builder" and data.get("mode") == "plan":
        task = data["task_id"]
        Path(".tollgate/plans").mkdir(parents=True, exist_ok=True)
        Path(f".tollgate/plans/{task}.md").write_text(PLAN.format(task=task,
                                                                  request=data["request"]))
        for tid, text in ((f"{task}-1", TICKET_T1), (f"{task}-2", TICKET_T2)):
            Path(f".tollgate/tickets/{tid}").mkdir(parents=True, exist_ok=True)
            Path(f".tollgate/tickets/{tid}/ticket.md").write_text(text.format(task=task))
        answer({"plan": f".tollgate/plans/{task}.md", "tickets": [f"{task}-1", f"{task}-2"]},
               cost)
    elif first == "# Role: builder" and data.get("mode") == "answer":
        answer({"answers": [{"finding": i, "action": opts.get("answer", "fix"), "evidence": "x"}
                            for i, _ in enumerate(data.get("findings", []))]}, cost)
    elif first == "# Role: builder":
        n = data["attempt"]
        die = opts.get("die_once")
        if die and n == 1 and not os.path.exists(die):
            Path(die).write_text("died")
            os.kill(os.getppid(), signal.SIGKILL)
            time.sleep(5)
        if mode == "slow":
            time.sleep(30)
        good = (mode == "pass2" and n >= 2) or mode == "pass1"
        if mode == "different" and n % 2 == 0:
            Path("app.py").write_text(GREET_BROKEN + SHOUT_OK)
        else:
            Path("app.py").write_text(GREET + (SHOUT_OK + WHISPER if good else SHOUT_BAD))
        if mode == "github":
            Path(".github/workflows").mkdir(parents=True, exist_ok=True)
            Path(".github/workflows/evil.yml").write_text("on: push\n")
            Path("app.py").write_text(GREET + SHOUT_OK)
        answer({"changed": ["app.py"], "locked_test_wrong": None}, cost)
    elif first == "# Role: reviewer" and "# Lens: test fit" in prompt:
        answer({"verdict": "pass", "findings": [], "items": []}, cost)
    elif first == "# Role: reviewer" and "# Lens: checklist" in prompt:
        lines = Path("app.py").read_text().splitlines()
        line = 999 if "badline" in sys.argv else next(
            i for i, text in enumerate(lines, 1) if '"""' in text)
        answer({"verdict": "pass", "findings": [],
                "items": [{"item": "C3", "passed": True, "file": "app.py", "line": line}]}, cost)
    elif first == "# Role: reviewer" and any(f"# Lens: {k}" in prompt for k in
                                             ("simplicity", "fresh reader", "readiness")):
        rounds = int(opts.get("planfind", 0))
        lens = prompt.split("# Lens: ", 1)[1].splitlines()[0]
        found = lens == "simplicity" and count_marker(".fake-planfind") <= rounds
        answer({"verdict": "pass", "findings": [{"level": "major", "text": "drop T-2?"}]
                if found else [], "items": []}, cost)
    elif first == "# Role: reviewer" and ("# Lens: change" in prompt or "# Lens: security" in prompt):
        lens = "security" if "# Lens: security" in prompt else "change"
        block = opts.get("block") == lens
        answer({"verdict": "fail" if block else "pass", "findings": [
            {"level": "blocking", "file": "app.py", "line": 1, "text": f"{lens} problem"}]
            if block else []}, cost)
    elif first == "# Role: advisor":
        decision = opts.get("plan_decision", "approve") if "plan" in data else opts.get(
            "decision", "park")
        answer({"decision": decision, "hint": "try harder", "reason": "test"}, cost)
    else:
        print(f"unknown role: {first}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
