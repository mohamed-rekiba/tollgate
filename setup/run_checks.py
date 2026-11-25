"""Run the project's checks before a push, side by side.

    uv run --no-project python .tollgate/checks/run_checks.py

setup.precommit writes one pre-push hook that runs this script, in place of one
hook for each check, because pre-commit runs hooks one after another. The script
reads the checks from .tollgate/settings.json in the working tree. The writing
check has a hook of its own, so it is left out here.

Each check runs with `sh -c` and its own time limit: its `minutes`, or else
`check_minutes`, or else 20. The setting `parallel` says how many checks run at
once: true for all of them, a whole number for that many, false for one at a
time in name order. When a check ends, the script prints its output, then one
line: PASS or FAIL, its name, and why it failed. It ends with 1 when a check
failed or ran out of time. It uses only the standard library.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SETTINGS = ".tollgate/settings.json"
DEFAULT_MINUTES = 20


def checks(settings: dict) -> list:
    """(name, command, minutes) for each check this script runs, in name order."""
    found = []
    default = settings.get("check_minutes", DEFAULT_MINUTES)
    for name, check in sorted(settings.get("checks", {}).items()):
        run = check.get("run", "")
        if name == "writing" or "check_writing.py" in run:
            continue
        found.append((name, run, check.get("minutes", default)))
    return found


def jobs(settings: dict, count: int) -> int:
    """How many checks run at once."""
    value = settings.get("parallel", True)
    if value is False:
        return 1
    if value is True:
        return max(count, 1)
    return max(1, min(int(value), max(count, 1)))


def run_one(name: str, command: str, minutes: float, cwd: str) -> dict:
    """Run one check. Return its name, output, code, seconds, and why it failed."""
    start = time.monotonic()
    proc = subprocess.Popen(["sh", "-c", command], cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=minutes * 60)
        why = "" if proc.returncode == 0 else f"exit code {proc.returncode}"
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)   # the check and every process it started
        out, _ = proc.communicate()
        why = f"ran out of time after {minutes:g} minutes"
    return {"name": name, "output": out.decode(errors="replace"), "why": why,
            "seconds": time.monotonic() - start}


def report(result: dict, lock: threading.Lock) -> None:
    with lock:
        print(f"--- {result['name']} ---")
        if result["output"]:
            print(result["output"].rstrip("\n"))
        state = "FAIL" if result["why"] else "PASS"
        reason = f": {result['why']}" if result["why"] else ""
        print(f"{state} {result['name']} ({result['seconds']:.1f}s){reason}", flush=True)


def main(root: str = ".") -> int:
    path = Path(root, SETTINGS)
    if not path.exists():
        print(f"run_checks: {SETTINGS} is missing, so no check runs")
        return 0
    settings = json.loads(path.read_text())
    found = checks(settings)
    lock = threading.Lock()
    results = []

    def one(item):
        result = run_one(*item, cwd=root)
        report(result, lock)
        return result

    with ThreadPoolExecutor(max_workers=jobs(settings, len(found))) as pool:
        results = list(pool.map(one, found))
    failed = [r["name"] for r in results if r["why"]]
    if failed:
        print(f"run_checks: failed: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
