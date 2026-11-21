"""Stage 1 proof on a repository where Tollgate is already set up.

    PYTHONPATH=. python3 tests/proof_gate_github.py owner/name [--cases lab-2,lab-3]

It never touches the main branch. Each case pushes its own branch tg/lab-<n>
from main with a ticket and failing tests, starts the freeze, then pushes a
build plus one bad change, opens a pull request, and reads the check
"tollgate gate". The gate must fail every case. It prints one JSON line for each
case, leaves the pull requests open for a person to close, and leaves the freeze
tags, which the tag ruleset keeps.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from setup.gh import Gh, GhError

TESTS = '''import unittest


class Lab(unittest.TestCase):
    def test_c1_shout(self):
        from lab.shout import shout
        self.assertEqual(shout("ann"), "ANN")

    def test_c2_matches_kept(self):
        from action.paths import matches
        self.assertTrue(matches("a/b.py", ["a/**"]))
'''
TICKET_TEXT = """---
id: {id}
plan: lab
seams: lab.shout.shout, action.paths.matches
tests: tests/test_{low}.py
---
## Current behavior
There is no shout function.

## Desired behavior
lab.shout.shout returns its text in capitals.

## Checklist
- [C1, must] shout("ann") returns "ANN".
- [C2, must, keeps behavior] matches("a/b.py", ["a/**"]) still returns True.
- [C3] shout has a docstring.

## Out of scope
Everything else. This ticket exists only to prove the gate.
"""
BUILD = {"lab/__init__.py": "", "lab/shout.py":
         'def shout(text):\n    """Return the text in capitals."""\n    return text.upper()\n'}


def bad_changes(low: str) -> dict:
    test = f"tests/test_{low}.py"
    return {
        "lab-2": ("edits a locked test", {test: TESTS.replace('"ANN"', 'shout("ann")')}),
        "lab-3": ("adds a skip mark to a locked test", {test: TESTS.replace(
            "    def test_c1_shout", "    @unittest.skip('later')\n    def test_c1_shout")}),
        "lab-4": ("adds a test settings file", {"pytest.ini": "[pytest]\naddopts = -k kept\n"}),
        "lab-5": ("touches a tier 4 path with no approval",
                  {"action/paths.py": None}),
    }


def sh(cwd, *args, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def write(root, files):
    for path, text in files.items():
        target = Path(root, path)
        if text is None:  # append one comment line to an existing file
            target.write_text(target.read_text() + "# lab-5: a tier 4 change\n")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def wait(probe, seconds=900):
    for _ in range(seconds // 10):
        found = probe()
        if found:
            return found
        time.sleep(10)
    raise TimeoutError("waited too long")


def gate(gh, repo, sha):
    def probe():
        runs = gh.get(f"repos/{repo}/commits/{sha}/check-runs?check_name=tollgate%20gate")
        done = [r for r in runs.get("check_runs", []) if r["status"] == "completed"]
        return done[0] if done else None
    check = wait(probe)
    return check["conclusion"], (check.get("output") or {}).get("summary", "")


def freeze(gh, repo, ticket):
    gh.api("POST", f"repos/{repo}/actions/workflows/tollgate-freeze.yml/dispatches",
           {"ref": "main", "inputs": {"ticket": ticket}})

    def probe():
        try:
            return gh.get(f"repos/{repo}/git/ref/tags/tg/freeze/{ticket}/1")
        except GhError as err:
            if err.status == 404:
                return None
            raise
    wait(probe)


def run(repo, cases, gh=None):
    gh = gh or Gh()
    out = []
    with tempfile.TemporaryDirectory() as d:
        sh(d, "git", "clone", "-q", f"https://github.com/{repo}.git", ".")
        for ticket in cases:
            low = ticket.replace("-", "_")
            branch = f"tg/{ticket}" if ticket != "no-ticket" else "lab-no-ticket"
            sh(d, "git", "checkout", "-q", "-B", branch, "origin/main")
            if ticket != "no-ticket":
                write(d, {f".tollgate/tickets/{ticket}/ticket.md":
                          TICKET_TEXT.format(id=ticket, low=low), f"tests/test_{low}.py": TESTS})
                sh(d, "git", "add", "-A")
                sh(d, "git", "commit", "-q", "-m", f"{ticket}: ticket and locked tests")
                sh(d, "git", "push", "-q", "-f", "origin", branch)
                freeze(gh, repo, ticket)
            what, extra = bad_changes(low).get(ticket, ("names no ticket", {}))
            write(d, {**BUILD, **extra})
            sh(d, "git", "add", "-A")
            sh(d, "git", "commit", "-q", "-m", f"{ticket}: build, and {what}")
            sh(d, "git", "push", "-q", "-f", "origin", branch)
            sha = sh(d, "git", "rev-parse", "HEAD").stdout.strip()
            pr = gh.api("POST", f"repos/{repo}/pulls", {
                "title": f"{ticket}: {what} (gate proof, do not merge)", "head": branch,
                "base": "main", "body": "Gate proof on GitHub. The gate must fail. Close it."})
            got, summary = gate(gh, repo, sha)
            out.append({"case": ticket, "what": what, "want": "failure", "got": got,
                        "holds": got == "failure", "pull_request": pr["number"],
                        "summary": summary})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository")
    parser.add_argument("--cases", default="lab-2,lab-3,lab-4,lab-5,no-ticket")
    args = parser.parse_args(argv)
    results = run(args.repository, args.cases.split(","))
    for line in results:
        print(json.dumps(line))
    return 0 if all(r["holds"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
