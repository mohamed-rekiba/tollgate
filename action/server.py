"""Ask GitHub for facts through the REST API, with the gh command.

Only REST paths are used, so the same calls work from a laptop, a workflow, and
a restricted session.
"""

import json
import subprocess


class ServerError(RuntimeError):
    pass


class Server:
    def __init__(self, repository: str):
        self.repository = repository

    def _get(self, path: str):
        proc = subprocess.run(
            ["gh", "api", "--paginate", f"repos/{self.repository}/{path}"],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise ServerError(f"GET {path}: {proc.stderr.strip()}")
        text = proc.stdout.strip()
        # --paginate joins JSON arrays page by page: ][ between pages.
        return json.loads(text.replace("]\n[", ",").replace("][", ",")) if text else None

    def run(self, run_id) -> dict:
        data = self._get(f"actions/runs/{run_id}")
        return {
            "path": data.get("path", ""),
            "head_branch": data.get("head_branch", ""),
            "event": data.get("event", ""),
            "conclusion": data.get("conclusion", ""),
        }

    def approvals(self, pr: int) -> list:
        out = []
        for review in self._get(f"pulls/{pr}/reviews") or []:
            out.append({
                "kind": "review", "user": review["user"]["login"],
                "user_type": review["user"]["type"], "state": review["state"],
                "commit": review.get("commit_id", ""), "body": "",
            })
        for comment in self._get(f"issues/{pr}/comments") or []:
            out.append({
                "kind": "comment", "user": comment["user"]["login"],
                "user_type": comment["user"]["type"], "state": "",
                "commit": "", "body": comment.get("body", "").strip(),
            })
        return out

    def pull(self, pr: int) -> dict:
        data = self._get(f"pulls/{pr}")
        return {"author": data["user"]["login"], "head": data["head"]["sha"]}

    def post_check(self, sha: str, name: str, passed: bool, title: str, text: str) -> None:
        """Create a finished check run on a commit."""
        body = {
            "name": name, "head_sha": sha, "status": "completed",
            "conclusion": "success" if passed else "failure",
            "output": {"title": title[:250], "summary": text[:60000] or title},
        }
        proc = subprocess.run(
            ["gh", "api", "-X", "POST", f"repos/{self.repository}/check-runs", "--input", "-"],
            input=json.dumps(body), capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise ServerError(f"POST check-runs: {proc.stderr.strip()}")

    def check_passed(self, sha: str, name: str):
        """Return True or False for the newest check run of that name, or None if absent."""
        data = self._get(f"commits/{sha}/check-runs")
        runs = [r for r in (data or {}).get("check_runs", []) if r["name"] == name]
        if not runs:
            return None
        newest = max(runs, key=lambda r: r.get("started_at") or "")
        return newest.get("conclusion") == "success"
