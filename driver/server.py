"""What the driver asks of the server.

The driver needs six things: start a freeze and wait for its tag, read a run,
open a pull request, wait for the gate, merge, and the facts the gate reads.
GitHub gives them through the REST API. Tests pass a fake with the same methods.
"""

import os
import subprocess
import time
from urllib.parse import quote

from action import manifest as mf
from action.server import Server
from setup.gh import Gh, GhError

WAIT_SECONDS = 1800


class GitHub(Server):
    def __init__(self, repository: str, gh=None, sleep=time.sleep):
        super().__init__(repository)
        self.gh = gh or Gh()
        self.sleep = sleep

    @classmethod
    def for_project(cls, project: str, repository: str | None = None) -> "GitHub":
        if not repository:
            url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=project,
                                 capture_output=True, text=True, check=True).stdout.strip()
            repository = url.removesuffix(".git").split("github.com")[-1].lstrip(":/")
        return cls(repository)

    def _wait(self, probe, what: str):
        for _ in range(WAIT_SECONDS // 15):
            found = probe()
            if found:
                return found
            self.sleep(15)
        raise TimeoutError(f"waited {WAIT_SECONDS} seconds for {what}")

    def _tags(self, ticket: str) -> set:
        try:
            # No trailing slash: some proxies refuse it. The prefix filter below
            # keeps lab-1 apart from lab-10.
            refs = self.gh.get(f"repos/{self.repository}/git/matching-refs/tags/tg/freeze/{ticket}")
        except GhError:
            return set()
        prefix = f"refs/tags/tg/freeze/{ticket}/"
        return {r["ref"] for r in refs or [] if r["ref"].startswith(prefix)}

    def freeze(self, ticket: str) -> str:
        """Start the freeze workflow and wait for a new tag. Raise FreezeError if the run fails."""
        before = self._tags(ticket)
        started = time.time()
        self.gh.api("POST", f"repos/{self.repository}/actions/workflows/tollgate.yml/dispatches",
                    {"ref": "main", "inputs": {"kind": "freeze", "id": ticket}})

        def probe():
            new = self._tags(ticket) - before
            if new:
                return max(new, key=lambda r: int(r.rsplit("/", 1)[1])).removeprefix("refs/tags/")
            runs = self.gh.get(f"repos/{self.repository}/actions/workflows/tollgate.yml/"
                               "runs?event=workflow_dispatch&per_page=5")
            for run in runs.get("workflow_runs", []):
                if (run.get("display_title") == f"tollgate freeze {ticket}"
                        and run["status"] == "completed" and run["conclusion"] != "success"
                        and run["created_at"] >= time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                               time.gmtime(started - 5))):
                    raise mf.FreezeError(f"the freeze run failed: {self._reason(run.get('id'))} "
                                         f"({run['html_url']})")
            return None
        return self._wait(probe, f"a freeze tag for {ticket}")

    def _reason(self, run_id) -> str:
        """The line of a failed run's log that says why, or a short note when it has none."""
        if not run_id:
            return "the run has no id"
        try:
            jobs = self.gh.get(f"repos/{self.repository}/actions/runs/{run_id}/jobs")
            failed = [j for j in jobs.get("jobs", []) if j.get("conclusion") == "failure"]
            if not failed:
                return "no job failed"
            log = subprocess.run(
                ["gh", "api", f"repos/{self.repository}/actions/jobs/{failed[0]['id']}/logs"],
                capture_output=True, text=True, check=False).stdout
        except (GhError, OSError, KeyError) as err:
            return f"its log could not be read: {err}"
        for line in log.splitlines():
            for marker in ("cannot be frozen", "Error", "error:"):
                if marker in line:
                    return line.split(" ", 1)[-1].strip()[:500]
        return f"job {failed[0].get('name')} failed"

    def open_pr(self, branch: str, title: str, body: str) -> int:
        existing = self.gh.get(f"repos/{self.repository}/pulls?state=open&head="
                               f"{quote(self.repository.split('/')[0])}:{quote(branch)}")
        if existing:
            number = existing[0]["number"]
        else:
            number = self.gh.api("POST", f"repos/{self.repository}/pulls", {
                "title": title, "head": branch, "base": "main", "body": body})["number"]
        self.start_check(number)
        return number

    def start_check(self, pr: int) -> None:
        """On GitHub Actions, start the gate for a pull request by hand. A pull request
        or comment made with the workflow's own token starts no other workflow, but a
        workflow_dispatch does. On a person's machine, GitHub starts it on its own."""
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return
        self.gh.api("POST", f"repos/{self.repository}/actions/workflows/tollgate.yml/dispatches",
                    {"ref": "main", "inputs": {"kind": "check", "id": str(pr)}})

    def wait_gate(self, sha: str) -> str:
        def probe():
            runs = self.gh.get(f"repos/{self.repository}/commits/{sha}/check-runs"
                               "?check_name=tollgate%20gate")
            done = [r for r in runs.get("check_runs", []) if r["status"] == "completed"]
            return done[0]["conclusion"] if done else None
        return self._wait(probe, "the check tollgate gate")

    def ask(self, title: str, body: str) -> int:
        try:
            self.gh.api("POST", f"repos/{self.repository}/labels",
                        {"name": "tg-waiting", "color": "d4a72c",
                         "description": "Tollgate waits for a decision by a person"})
        except GhError:
            pass  # the label exists
        return self.gh.api("POST", f"repos/{self.repository}/issues",
                           {"title": title, "body": body, "labels": ["tg-waiting"]})["number"]

    def issue_comments(self, issue: int) -> list:
        return [{"user": c["user"]["login"], "user_type": c["user"]["type"],
                 "body": c.get("body", "")}
                for c in self.gh.get(f"repos/{self.repository}/issues/{issue}/comments") or []]

    def close_question(self, issue: int) -> None:
        self.gh.api("PATCH", f"repos/{self.repository}/issues/{issue}",
                    {"state": "closed", "labels": []})

    def lock_plan(self, task: str) -> str:
        """Start the plan workflow and wait for a new plan tag."""
        prefix = f"refs/tags/tg/plan/{task}/"

        def tags():
            try:
                refs = self.gh.get(f"repos/{self.repository}/git/matching-refs/tags/tg/plan/{task}")
            except GhError:
                return set()
            return {r["ref"] for r in refs or [] if r["ref"].startswith(prefix)}
        before = tags()
        self.gh.api("POST", f"repos/{self.repository}/actions/workflows/tollgate.yml/dispatches",
                    {"ref": "main", "inputs": {"kind": "plan", "id": task}})

        def probe():
            new = tags() - before
            return max(new, key=lambda r: int(r.rsplit("/", 1)[1])).removeprefix("refs/tags/") \
                if new else None
        return self._wait(probe, f"a plan tag for {task}")

    def merge(self, pr: int) -> None:
        self.gh.api("PUT", f"repos/{self.repository}/pulls/{pr}/merge", {"merge_method": "squash"})
