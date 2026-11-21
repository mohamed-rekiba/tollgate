"""A small client for the GitHub REST API, through the gh command.

The setup scripts take a client as an argument, so tests can pass a fake one.
"""

import json
import subprocess


class GhError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Gh:
    def api(self, method: str, path: str, body=None):
        args = ["gh", "api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        if body is not None:
            args += ["--input", "-"]
        proc = subprocess.run(args, input=json.dumps(body) if body is not None else None,
                              capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            status = 404 if "404" in proc.stderr else 403 if "403" in proc.stderr else 1
            # gh prints GitHub's error body, which names the bad field, on standard output.
            detail = proc.stdout.strip()
            raise GhError(status, f"{method} {path}: {proc.stderr.strip()}"
                          + (f"\n{detail}" if detail else ""))
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def get(self, path: str):
        return self.api("GET", path)
