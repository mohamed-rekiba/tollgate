"""What the driver asks of the server.

The driver needs six things: start a freeze and wait for its tag, read a run,
open a pull request, wait for the gate, merge, and the facts the gate reads.
GitHub gives them through the REST API. Tests pass a fake with the same methods.
"""

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
        self.gh.api("POST", f"repos/{self.repository}/actions/workflows/tollgate-freeze.yml/"
                    "dispatches", {"ref": "main", "inputs": {"ticket": ticket}})

        def probe():
            new = self._tags(ticket) - before
            if new:
                return max(new, key=lambda r: int(r.rsplit("/", 1)[1])).removeprefix("refs/tags/")
            runs = self.gh.get(f"repos/{self.repository}/actions/workflows/tollgate-freeze.yml/"
                               "runs?event=workflow_dispatch&per_page=5")
            for run in runs.get("workflow_runs", []):
                if (run["status"] == "completed" and run["conclusion"] != "success"
                        and run["created_at"] >= time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                               time.gmtime(started - 5))):
                    raise mf.FreezeError(f"the freeze run failed: {run['html_url']}")
            return None
        return self._wait(probe, f"a freeze tag for {ticket}")

    def open_pr(self, branch: str, title: str, body: str) -> int:
        existing = self.gh.get(f"repos/{self.repository}/pulls?state=open&head="
                               f"{quote(self.repository.split('/')[0])}:{quote(branch)}")
        if existing:
            return existing[0]["number"]
        return self.gh.api("POST", f"repos/{self.repository}/pulls",
                           {"title": title, "head": branch, "base": "main", "body": body})["number"]

    def wait_gate(self, sha: str) -> str:
        def probe():
            runs = self.gh.get(f"repos/{self.repository}/commits/{sha}/check-runs"
                               "?check_name=tollgate%20gate")
            done = [r for r in runs.get("check_runs", []) if r["status"] == "completed"]
            return done[0]["conclusion"] if done else None
        return self._wait(probe, "the check tollgate gate")

    def merge(self, pr: int) -> None:
        self.gh.api("PUT", f"repos/{self.repository}/pulls/{pr}/merge", {"merge_method": "squash"})
