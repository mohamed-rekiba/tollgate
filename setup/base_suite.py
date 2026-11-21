"""Run the base suite: the five things every project base must prove.

Each is one command under `base` in the settings, and each must end with 0:

checks_run         the project's checks run
parallel_tests     the tests run side by side, for example pytest -n 4
env_up_down        the test environment starts and stops, for example docker compose up and down
bad_setting_stops  a start with a wrong setting stops with an error; the command
                   ends with 0 when the start failed as it should
one_log_line       one request writes one structured log line

A command that is not set fails, so a new project's base starts with five gaps,
and each gap becomes a ticket.
"""

import argparse
import json
import subprocess
import sys

from action import settings as st

NAMES = ("checks_run", "parallel_tests", "env_up_down", "bad_setting_stops", "one_log_line")


def run(settings: dict, workdir: str, minutes: float = 10, only: str = "") -> list:
    out = []
    for name in NAMES:
        if only and name != only:
            continue
        command = settings["base"].get(name, "")
        if not command:
            out.append({"name": name, "passed": False, "why": "not set"})
            continue
        try:
            proc = subprocess.run(command, shell=True, cwd=workdir, capture_output=True,
                                  text=True, timeout=minutes * 60, check=False)
        except subprocess.TimeoutExpired:
            out.append({"name": name, "passed": False, "why": f"ran past {minutes} minutes"})
            continue
        out.append({"name": name, "passed": proc.returncode == 0,
                    "why": "" if proc.returncode == 0 else
                    f"ended with {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-300:]}"})
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="base_suite", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--settings", default=st.PATH)
    parser.add_argument("--only", metavar="NAME", help="run one check: " + ", ".join(NAMES))
    args = parser.parse_args(argv)
    if args.only is not None and args.only not in NAMES:
        print(f"unknown check {args.only!r}; the five are: {', '.join(NAMES)}", file=sys.stderr)
        return 1
    with open(f"{args.project}/{args.settings}") as f:
        settings = st.parse(f.read())
    results = run(settings, args.project, only=args.only or "")
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
