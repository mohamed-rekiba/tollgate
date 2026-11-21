"""Prove that the gate rejects a change to a locked test.

Before you run it, the branch tg/<ticket> must be on the server with a ticket
and failing tests for it. /tollgate:init writes them. The script then:

1. starts the freeze workflow for the ticket and waits for the freeze tag,
2. pushes a commit that adds one empty line to a locked file,
3. opens a pull request and waits for the check "tollgate gate",
4. passes only if that check failed on rule 3,
5. closes the pull request and deletes the branch. The freeze tag stays,
   because the tag ruleset stops anyone from deleting it.
"""

import argparse
import json
import subprocess
import sys
import time

from action import manifest as mf
from setup.gh import Gh, GhError

WAIT_SECONDS = 900


def _git(project, *args):
    return subprocess.run(["git", *args], cwd=project, check=True, capture_output=True,
                          text=True).stdout.strip()


def _wait(probe, what: str, sleep, seconds: int):
    waited = 0
    while waited <= seconds:
        found = probe()
        if found:
            return found
        sleep(15)
        waited += 15
    raise TimeoutError(f"waited {seconds} seconds for {what}")


def prove(gh, repository: str, ticket: str, project: str = ".", git=_git, sleep=time.sleep,
          seconds: int = WAIT_SECONDS, keep_branch: bool = False) -> dict:
    branch = f"tg/{ticket}"
    tag = f"tg/freeze/{ticket}/1"
    def tag_message():
        try:
            ref = gh.get(f"repos/{repository}/git/ref/tags/{tag}")
        except GhError as err:
            if err.status == 404:
                return None
            raise
        return gh.get(f"repos/{repository}/git/tags/{ref['object']['sha']}")["message"]

    # A second run reuses the freeze it made, so it gives the same result.
    if tag_message() is None:
        gh.api("POST", f"repos/{repository}/actions/workflows/tollgate-freeze.yml/dispatches",
               {"ref": "main", "inputs": {"ticket": ticket}})
    manifest = mf.loads(_wait(tag_message, f"the tag {tag}", sleep, seconds))
    locked = min(p for p in manifest["files"] if not p.endswith("ticket.md"))
    git(project, "fetch", "origin", branch)
    git(project, "switch", "-C", branch, "FETCH_HEAD")
    with open(f"{project}/{locked}", "a") as f:
        f.write("\n")
    git(project, "commit", "-am", "proof: change a locked test")
    git(project, "push", "origin", branch)
    head = git(project, "rev-parse", "HEAD")
    pr = gh.api("POST", f"repos/{repository}/pulls", {
        "title": f"Tollgate proof {ticket}: the gate must reject this", "head": branch,
        "base": "main", "body": "Opened by setup/prove_gate.py. It closes on its own."})["number"]

    def gate_check():
        runs = gh.get(f"repos/{repository}/commits/{head}/check-runs?check_name=tollgate%20gate")
        done = [r for r in runs.get("check_runs", []) if r["status"] == "completed"]
        return done[0] if done else None

    try:
        check = _wait(gate_check, "the check tollgate gate", sleep, seconds)
    finally:
        gh.api("PATCH", f"repos/{repository}/pulls/{pr}", {"state": "closed"})
        try:
            if keep_branch:
                raise GhError(0, "keep the branch")
            gh.api("DELETE", f"repos/{repository}/git/refs/heads/{branch}")
        except GhError:
            pass
    summary = (check.get("output") or {}).get("summary", "")
    passed = check["conclusion"] == "failure" and "Rule 3" in summary
    return {"proof": "passed" if passed else "failed", "pull_request": pr,
            "locked_file": locked, "gate": check["conclusion"], "summary": summary}


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="prove_gate", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repository", help="owner/name")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--project", default=".")
    parser.add_argument("--keep-branch", action="store_true", help="do not delete the branch")
    args = parser.parse_args(argv)
    try:
        result = prove(gh or Gh(), args.repository, args.ticket, args.project,
                       keep_branch=args.keep_branch)
    except (GhError, TimeoutError, subprocess.CalledProcessError, ValueError) as err:
        print(json.dumps({"proof": "failed", "reason": str(err)}))
        return 1
    print(json.dumps(result))
    return 0 if result["proof"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
