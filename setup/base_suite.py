"""The base suite: the five things every project base must prove.

The roadmap runs it after a large request's base tasks finish (driver/roadmap.py).

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

import subprocess

from action.checks import project_env

NAMES = ("checks_run", "parallel_tests", "env_up_down", "bad_setting_stops", "one_log_line")


def run(settings: dict, workdir: str, minutes: float = 10) -> list:
    out = []
    for name in NAMES:
        command = settings["base"].get(name, "")
        if not command:
            out.append({"name": name, "passed": False, "why": "not set"})
            continue
        try:
            # The project's own commands, from the settings on main, with no token:
            # the same environment the project's checks get.
            proc = subprocess.run(command, shell=True, cwd=workdir, capture_output=True,
                                  text=True, timeout=minutes * 60, check=False, env=project_env())
        except subprocess.TimeoutExpired:
            out.append({"name": name, "passed": False, "why": f"ran past {minutes} minutes"})
            continue
        out.append({"name": name, "passed": proc.returncode == 0,
                    "why": "" if proc.returncode == 0 else
                    f"ended with {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-300:]}"})
    return out
