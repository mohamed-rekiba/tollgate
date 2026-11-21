"""Stage 1 proof. Run it by hand against an empty lab repository where you are admin.

    PYTHONPATH=. python3 tests/proof_stage1.py owner/lab-repo --ref <tollgate commit>

It writes a small Python project to the main branch, sets up Tollgate, and then:

- LAB-1: an honest build. The gate must pass.
- LAB-2: the build also edits a locked test. The gate must fail.
- LAB-3: the build also adds a skip mark to a locked test. The gate must fail.
- LAB-4: the build also adds a test settings file. The gate must fail.
- LAB-5: the build also touches a tier 4 path with no approval. The gate must fail.
- a branch that names no ticket. The gate must fail.
- a freeze tag pushed from this machine. The server must reject it.

It prints one JSON line for each case and ends with 0 only when every case holds.
This is not run by CI. It changes the lab repository and leaves its branches and
tags there.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from setup import apply_rulesets, write_workflows
from setup.gh import Gh, GhError

SETTINGS = {
    "setup": [("python3 -m pip install --quiet --user pytest || "
               "python3 -m pip install --quiet --break-system-packages pytest")],
    "checks": {"tests": {"run": "python3 -m pytest -q --junitxml=report.xml",
                         "report": "report.xml"}},
    "tiers": {"4": ["migrations/**"]},
    "require_plan": False,
    "auto_merge": False,
}
APP = 'def greet(name):\n    return f"hello {name}"\n'
BUILT = APP + '\n\ndef shout(name):\n    return greet(name).upper()\n'

TICKET = """---
id: {id}
plan: lab
seams: app.shout
tests: tests/test_{low}.py
---
## Current behavior
There is no shout.

## Desired behavior
shout returns the greeting in capitals.

## Checklist
- [C1, must] shout("ann") returns "HELLO ANN".
- [C2, must, keeps behavior] greet("ann") still returns "hello ann".
- [C3] shout takes one argument.

## Out of scope
Other languages.
"""
TESTS = """import app


def test_c1_shout():
    assert app.shout("ann") == "HELLO ANN"


def test_c2_greet_kept():
    assert app.greet("ann") == "hello ann"


def test_c3_one_argument():
    assert app.shout.__code__.co_argcount == 1
"""

# Each case: ticket id or None, extra files the build adds, the result the gate must give.
CASES = [
    ("LAB-1", {}, "success"),
    ("LAB-2", {"tests/test_lab_2.py": TESTS.replace('"HELLO ANN"', 'app.shout("ann")')},
     "failure"),
    ("LAB-3", {"tests/test_lab_3.py": "import pytest\n" + TESTS.replace(
        "def test_c1_shout", "@pytest.mark.skip\ndef test_c1_shout")}, "failure"),
    ("LAB-4", {"pytest.ini": "[pytest]\naddopts = -k greet\n"}, "failure"),
    ("LAB-5", {"migrations/0001.sql": "select 1;\n"}, "failure"),
    (None, {}, "failure"),
]


def sh(cwd, *args, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


def write(root, files: dict):
    for path, text in files.items():
        target = Path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def wait(probe, seconds=900):
    for _ in range(seconds // 15):
        found = probe()
        if found:
            return found
        time.sleep(15)
    raise TimeoutError("waited too long")


def gate_result(gh, repo, sha):
    def probe():
        runs = gh.get(f"repos/{repo}/commits/{sha}/check-runs?check_name=tollgate%20gate")
        done = [r for r in runs.get("check_runs", []) if r["status"] == "completed"]
        return done[0] if done else None
    check = wait(probe)
    return check["conclusion"], (check.get("output") or {}).get("summary", "")


def freeze(gh, repo, ticket):
    gh.api("POST", f"repos/{repo}/actions/workflows/tollgate.yml/dispatches",
           {"ref": "main", "inputs": {"kind": "freeze", "id": ticket}})

    def probe():
        try:
            return gh.get(f"repos/{repo}/git/ref/tags/tg/freeze/{ticket}/1")
        except GhError as err:
            if err.status == 404:
                return None
            raise
    wait(probe)


def run(repo: str, ref: str, gh=None) -> list:
    gh = gh or Gh()
    out = []
    with tempfile.TemporaryDirectory() as d:
        sh(d, "git", "clone", "-q", f"https://github.com/{repo}.git", ".")
        sh(d, "git", "checkout", "-q", "-B", "main")
        write(d, {"app.py": APP, ".tollgate/settings.json": json.dumps(SETTINGS, indent=2),
                  "tests/__init__.py": "", "conftest.py": "import sys\nsys.path.insert(0, '.')\n"})
        write_workflows.write(d, ref)
        sh(d, "git", "add", "-A")
        sh(d, "git", "commit", "-q", "-m", "lab: sample project with Tollgate")
        sh(d, "git", "push", "-q", "origin", "main")
        for line in apply_rulesets.apply(gh, repo):
            out.append({"case": "rulesets", "result": line})
        for ticket, extra, want in CASES:
            branch = f"tg/{ticket}" if ticket else "lab-no-ticket"
            sh(d, "git", "checkout", "-q", "-B", branch, "origin/main")
            if ticket:
                low = ticket.lower().replace("-", "_")
                write(d, {f".tollgate/tickets/{ticket}/ticket.md": TICKET.format(id=ticket, low=low),
                          f"tests/test_{low}.py": TESTS})
                sh(d, "git", "add", "-A")
                sh(d, "git", "commit", "-q", "-m", f"{ticket}: ticket and tests")
                sh(d, "git", "push", "-q", "origin", branch)
                freeze(gh, repo, ticket)
            write(d, {"app.py": BUILT, **extra})
            sh(d, "git", "add", "-A")
            sh(d, "git", "commit", "-q", "-m", "build")
            sh(d, "git", "push", "-q", "origin", branch)
            sha = sh(d, "git", "rev-parse", "HEAD").stdout.strip()
            pr = gh.api("POST", f"repos/{repo}/pulls", {
                "title": f"lab {branch}", "head": branch, "base": "main", "body": "stage 1 proof"})
            got, summary = gate_result(gh, repo, sha)
            out.append({"case": branch, "want": want, "got": got, "holds": got == want,
                        "pull_request": pr["number"], "summary": summary})
        sh(d, "git", "tag", "tg/freeze/LAB-1/9", "origin/main")
        pushed = sh(d, "git", "push", "origin", "tg/freeze/LAB-1/9", check=False)
        out.append({"case": "tag from this machine", "want": "rejected",
                    "got": "rejected" if pushed.returncode else "accepted",
                    "holds": pushed.returncode != 0})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository")
    parser.add_argument("--ref", required=True, help="full commit id of Tollgate to pin")
    args = parser.parse_args(argv)
    results = run(args.repository, args.ref)
    for line in results:
        print(json.dumps(line))
    return 0 if all(r.get("holds", True) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
