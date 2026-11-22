"""Check a commit message. Python 3, standard library only.

Tollgate copies this file into a project as .tollgate/checks/check_commit_msg.py.
pre-commit runs it on each commit message, with the path of the message file:

    python3 .tollgate/checks/check_commit_msg.py .git/COMMIT_EDITMSG

The subject has the form `type(scope): subject`, and no line credits an AI: the
author is the owner of the repository. The subject git writes for a merge, such
as "Merge branch 'x'", passes only while a merge is in progress.

It ends with 0 when the message passes, and 1 with one line for each problem.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

TYPES = "feat|fix|docs|test|refactor|chore|build|ci|perf|style|revert"
SUBJECT = re.compile(rf"^({TYPES})\([^()\s]+\)!?: \S")
AI_CREDIT = re.compile(r"co-authored-by:.*\b(claude|anthropic|openai|chatgpt|copilot|gemini)\b"
                       r"|generated (with|by) .*\b(claude|chatgpt|copilot|gemini|ai)\b"
                       r"|\U0001F916", re.IGNORECASE)
SCISSORS = "# ------------------------ >8 ------------------------"


def merging() -> bool:
    proc = subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
                          capture_output=True, check=False)
    return proc.returncode == 0 or any(k.startswith("GITHEAD_") for k in os.environ)


def problems(message: str, in_merge: bool = False) -> list:
    lines = []
    for line in message.splitlines():
        if line.startswith(SCISSORS):
            break
        if not line.startswith("#"):
            lines.append(line)
    body = [x for x in lines if x.strip()]
    subject = body[0].strip() if body else ""
    found = []
    if not (in_merge and subject.startswith("Merge ")) and not SUBJECT.match(subject):
        found.append(f"subject '{subject[:60]}' is not 'type(scope): subject', with a type "
                     f"from: {TYPES.replace('|', ', ')}.")
    for line in lines:
        if AI_CREDIT.search(line):
            found.append(f"'{line.strip()[:60]}' credits an AI. The author is the owner of "
                         "the repository.")
    return found


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    path = Path(argv[0]) if argv else Path(".git/COMMIT_EDITMSG")
    found = problems(path.read_text(errors="replace"), merging())
    for line in found:
        print(f"check_commit_msg: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
