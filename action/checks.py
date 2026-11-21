"""Run the check commands of a project and collect their results."""

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from action import junit


@dataclass
class CheckResult:
    name: str
    passed: bool
    timed_out: bool = False
    output: str = ""


@dataclass
class Results:
    checks: list = field(default_factory=list)
    tests: dict = field(default_factory=dict)  # test id -> {"status", "file"}

    def failed_checks(self):
        return sorted(c.name for c in self.checks if not c.passed)

    def to_json(self) -> str:
        return json.dumps({"checks": [asdict(c) for c in self.checks], "tests": self.tests}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Results":
        data = json.loads(text)
        return cls([CheckResult(**c) for c in data["checks"]], data["tests"])


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.splitlines()[-lines:])


def run(settings: dict, workdir, only=None) -> Results:
    """Run each check in the folder and read each test report it names.

    A check that runs longer than its limit counts as failed.
    """
    results = Results()
    for name, check in settings["checks"].items():
        if only and name not in only:
            continue
        minutes = check.get("minutes", settings["check_minutes"])
        report = Path(workdir, check["report"]) if check.get("report") else None
        if report and report.exists():
            report.unlink()
        try:
            proc = subprocess.run(
                check["run"], shell=True, cwd=workdir, capture_output=True, text=True, check=False,
                timeout=minutes * 60,
            )
            result = CheckResult(name, proc.returncode == 0, False, _tail(proc.stdout + proc.stderr))
        except subprocess.TimeoutExpired:
            result = CheckResult(name, False, True, f"ran longer than {minutes} minutes")
        results.checks.append(result)
        if report and report.exists():
            for test_id, test in junit.read(report).items():
                results.tests[test_id] = {"status": test.status, "file": test.file}
    return results


def main(argv=None) -> int:
    from action import settings as st

    parser = argparse.ArgumentParser(prog="tollgate checks", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main", help="read the settings from here")
    parser.add_argument("--only", action="append", help="run only this check")
    parser.add_argument("--setup", action="store_true", help="run the setup commands first")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    settings = st.load_from_ref(args.repo, args.base)
    if args.setup:
        for command in settings["setup"]:
            subprocess.run(command, shell=True, cwd=args.repo, check=True)
    results = run(settings, args.repo, args.only)
    with open(args.out, "w") as f:
        f.write(results.to_json())
    for check in results.checks:
        print(f"{check.name}: {'passed' if check.passed else 'failed'}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
