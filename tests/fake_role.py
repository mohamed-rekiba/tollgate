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
GREET_BROKEN = 'def greet(name):\n    return f"hi {name}"\n'
TESTS = '''import unittest

import app


class T(unittest.TestCase):
    def test_c1_shout(self):
        self.assertEqual(app.shout("ann"), "HELLO ANN")

    def test_c2_greet_kept(self):
        self.assertEqual(app.greet("ann"), "hello ann")
'''


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
        Path("tests/test_t1.py").write_text(TESTS)
        answer({"tests": [{"item": "C1", "file": "tests/test_t1.py", "name": "test_c1_shout"},
                          {"item": "C2", "file": "tests/test_t1.py", "name": "test_c2_greet_kept"}]},
               cost)
    elif first == "# Role: builder":
        n = data["attempt"]
        die = opts.get("die_once")
        if die and n == 1 and not os.path.exists(die):
            Path(die).write_text("died")
            os.kill(os.getppid(), signal.SIGKILL)
            time.sleep(5)
        if mode == "slow":
            time.sleep(30)
        good = mode == "pass2" and n >= 2
        if mode == "different" and n % 2 == 0:
            Path("app.py").write_text(GREET_BROKEN + SHOUT_OK)
        else:
            Path("app.py").write_text(GREET + (SHOUT_OK if good else SHOUT_BAD))
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
    elif first == "# Role: advisor":
        answer({"decision": opts.get("decision", "park"), "hint": "try harder", "reason": "test"},
               cost)
    else:
        print(f"unknown role: {first}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
