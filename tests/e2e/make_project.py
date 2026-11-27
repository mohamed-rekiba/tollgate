"""Make a throwaway project for an end-to-end run of Tollgate with real subagents.

    python3 tests/e2e/make_project.py <empty folder>

It makes, under the folder:

    project/   a git repository on main: calc.py, its tests, and Tollgate set up
               by setup.init, with a tests check: the hook check-tests, which runs pytest
    state/     the state folder root, for TOLLGATE_STATE
    keys/      the key folder, with the machine secret, for TOLLGATE_KEYS
    gitconfig  a git identity for the run, for GIT_CONFIG_GLOBAL

and writes the request of the task, .tollgate/requests/e2e-divide.md. Then it
prints the commands that run the task through driver.step next and answer.
The run needs a model, so no test runs it; tests/test_e2e_project.py checks only
that the project is made and that next names a first step.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

TG = Path(__file__).resolve().parents[2]
if str(TG) not in sys.path:
    sys.path.insert(0, str(TG))

TASK = "e2e-divide"
REQUEST = ("Add divide(a, b) to calc.py. It returns a divided by b, and raises "
           "ValueError with the message \"cannot divide by zero\" when b is 0.\n")
CALC = '''"""Small sums."""


def add(a, b):
    return a + b


def subtract(a, b):
    return a - b
'''
TESTS = '''from calc import add, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2
'''
GITCONFIG = ("[user]\n\tname = Tollgate e2e\n\temail = e2e@example.com\n"
             "[commit]\n\tgpgsign = false\n[init]\n\tdefaultBranch = main\n")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def make(root, which=shutil.which, install=True) -> dict:
    """Make the project under root, an empty or missing folder. Set TOLLGATE_STATE,
    TOLLGATE_KEYS, and GIT_CONFIG_GLOBAL in os.environ for it. Return its paths."""
    root = Path(root).resolve()
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"make_project: {root} is not empty; give a new folder")
    paths = {"root": root, "project": root / "project", "state": root / "state",
             "keys": root / "keys", "gitconfig": root / "gitconfig"}
    for name in ("project", "state", "keys"):
        paths[name].mkdir(parents=True)
    paths["gitconfig"].write_text(GITCONFIG)
    env = {"TOLLGATE_STATE": str(paths["state"]), "TOLLGATE_KEYS": str(paths["keys"]),
           "GIT_CONFIG_GLOBAL": str(paths["gitconfig"]), "GIT_CONFIG_NOSYSTEM": "1"}
    os.environ.update(env)
    paths["env"] = env

    p = paths["project"]
    _git(p, "init", "-q", "-b", "main")
    (p / "calc.py").write_text(CALC)
    (p / "tests").mkdir()
    (p / "tests" / "test_calc.py").write_text(TESTS)
    (p / ".gitignore").write_text("report.xml\n__pycache__/\n.pytest_cache/\n")
    _git(p, "add", "-A")
    _git(p, "commit", "-q", "-m", "feat(calc): add and subtract")

    from setup import init
    paths["init"] = init.init(str(p), which=which, install=install)
    request = p / ".tollgate" / "requests" / f"{TASK}.md"
    request.parent.mkdir(parents=True)
    request.write_text(REQUEST)
    paths["request"] = request
    return paths


def commands(paths: dict) -> str:
    env = " ".join(f"{k}={v}" for k, v in paths["env"].items())
    step = 'PYTHONPATH="$TG" python3 -P -m driver.step'
    return f"""The project is ready: {paths['project']}
Setup said:
  {chr(10).join('  ' + line for line in paths['init']).strip()}

1. In a new shell, set the run's folders and start Claude Code with this clone
   of Tollgate as its plugin:

   export TG={TG} {env}
   cd {paths['project']}
   claude --plugin-dir "$TG"

2. In that session, either type /tollgate:task with the request below, or run the
   loop of the task skill (skills/task/SKILL.md, step 4) by hand. The request is
   in {paths['request']}:

   {REQUEST.strip()}

   {step} next --project . --task {TASK}

   It prints one JSON object:

   - a step, with agent, prompt, cwd, key, and nonce: the main session starts the
     subagent named in agent (such as tollgate:analyst) with this message: the line
     "Your folder: <cwd>", a blank line, then prompt exactly as printed. It writes
     the subagent's whole final answer, unchanged, to a file outside the project,
     then runs:

     {step} answer --project . --key "<key>" --nonce "<nonce>" < "$TMPDIR/tollgate-answer.md"

     which prints the next object.
   - a question, with n, title, body, and options: you, the owner, pick one:

     PYTHONPATH="$TG" python3 -P -m setup.inbox --project . answer <n> <option>

     then run next again.
   - done, parked, or an error: the run ends. The report is in the state folder:
     {paths['state']}

3. When you are done, delete {paths['root']}.
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="make_project", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", help="a new or empty folder for the run")
    args = parser.parse_args(argv)
    from setup import init
    try:
        paths = make(args.folder)
    except init.InitError as err:
        print(f"make_project: {err}", file=sys.stderr)
        return 1
    print(commands(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
