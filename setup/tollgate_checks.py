"""Run the checks of one git hook stage, side by side: Tollgate's, and at a push, the project's.

    uv run --no-project python .tollgate/checks/tollgate_checks.py [stage] [file ...]

setup.precommit writes one pre-commit entry, for all four git steps, and it runs this
one script. pre-commit does not tell a hook which step runs it, so the script works the
step out, when no stage is named:

- pre-push, when pre-commit gives the name of the remote (PRE_COMMIT_REMOTE_NAME);
- commit-msg, when the first argument is a commit message file, such as COMMIT_EDITMSG;
- pre-merge-commit, when git names the commits it merges (GITHEAD_<commit>);
- pre-commit, in any other case.

A stage that is named as the first argument is used as it is. The checks of each stage are:

- pre-commit: check_locked.py, and check_writing.py --staged;
- commit-msg: check_commit_msg.py, with the message file that pre-commit passes;
- pre-merge-commit: check_locked.py, and check_merge.py merge;
- pre-push: check_merge.py push, and each check under `checks` in
  .tollgate/settings.json, except the writing check, which runs at a commit.

Each check runs in its own process with the Python that runs this script, and the
checks of a stage run side by side. The setting `parallel` in
.tollgate/settings.json says how many run at once: true, the default, for all of
them, a whole number for that many, false for one at a time. When a check ends,
the script prints its output, then one line: PASS or FAIL and its name. It ends
with 1 when a check failed. A project check runs with its own command, through `sh -c`,
from the project folder. It uses only the standard library.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETTINGS = ".tollgate/settings.json"

STAGE_WORD = re.compile(r"^[a-z]+(-[a-z]+)+$")   # a mistyped stage, such as post-commit
MESSAGE_FILES = ("COMMIT_EDITMSG", "MERGE_MSG", "SQUASH_MSG", "TAG_EDITMSG")

STAGES = {
    "pre-commit": [("locked", ["check_locked.py"]),
                   ("writing", ["check_writing.py", "--staged"])],
    "commit-msg": [("commit message", ["check_commit_msg.py"])],
    "pre-merge-commit": [("locked", ["check_locked.py"]),
                         ("merge", ["check_merge.py", "merge"])],
    "pre-push": [("push", ["check_merge.py", "push"])],
}
# The stages whose files pre-commit passes on to the check.
TAKES_FILES = ("commit-msg",)


def stage_of(args: list, env) -> tuple:
    """(stage, files) for a run that names no stage: the git step, worked out from what
    pre-commit and git give the hook."""
    if env.get("PRE_COMMIT_REMOTE_NAME"):
        return "pre-push", []
    if args and Path(args[0]).name in MESSAGE_FILES:
        return "commit-msg", args
    if any(name.startswith("GITHEAD_") for name in env):
        return "pre-merge-commit", []
    return "pre-commit", []


def project_checks(root: str) -> list:
    """(name, argv) for each check of the project under `checks` in the settings, with its
    own command. The writing check is one of Tollgate's own, so it is left out."""
    try:
        checks = json.loads(Path(root, SETTINGS).read_text()).get("checks", {})
    except (OSError, ValueError, AttributeError):
        return []
    found = []
    for name, check in sorted(checks.items()):
        run = check.get("run", "") if isinstance(check, dict) else ""
        if run and name != "writing" and "check_writing.py" not in run:
            found.append((f"check: {name}", ["sh", "-c", run]))
    return found


def commands(stage: str, files=(), root: str = ".") -> list:
    """(name, argv) for each check of the stage. A push also runs the project's checks."""
    found = []
    for name, (script, *args) in STAGES[stage]:
        argv = [sys.executable, str(HERE / script), *args]
        if stage in TAKES_FILES:
            argv += list(files)
        found.append((name, argv))
    if stage == "pre-push":
        found += project_checks(root)
    return found


def jobs(root: str, count: int) -> int:
    """How many checks run at once, from the setting `parallel`."""
    try:
        value = json.loads(Path(root, SETTINGS).read_text()).get("parallel", True)
    except (OSError, ValueError):
        value = True
    if value is False:
        return 1
    if value is True or not isinstance(value, int) or value < 1:
        return max(count, 1)
    return max(1, min(value, count))


def run_one(name: str, argv: list, cwd: str, stdin) -> dict:
    """Run one check. Return its name, output, and code."""
    start = time.monotonic()
    proc = subprocess.run(argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          stdin=stdin, check=False)
    return {"name": name, "output": proc.stdout.decode(errors="replace"),
            "code": proc.returncode, "seconds": time.monotonic() - start}


def report(result: dict, lock: threading.Lock) -> None:
    with lock:
        if result["output"]:
            print(result["output"].rstrip("\n"))
        state = "PASS" if result["code"] == 0 else "FAIL"
        print(f"{state} {result['name']} ({result['seconds']:.1f}s)", flush=True)


def main(argv=None, root: str = ".") -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in STAGES:
        stage, files = argv[0], argv[1:]
    elif argv and STAGE_WORD.match(argv[0]):
        print(f"tollgate_checks: not a stage: {argv[0]}. Stages: {', '.join(STAGES)}",
              file=sys.stderr)
        return 2
    else:
        stage, files = stage_of(argv, os.environ)
    found = commands(stage, files, root)
    # One check may read the input pre-commit gives the hook. Two would race for it.
    stdin = None if len(found) == 1 else subprocess.DEVNULL
    lock = threading.Lock()

    def one(item):
        result = run_one(*item, cwd=root, stdin=stdin)
        report(result, lock)
        return result

    with ThreadPoolExecutor(max_workers=jobs(root, len(found))) as pool:
        results = list(pool.map(one, found))
    return 1 if any(r["code"] != 0 for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
