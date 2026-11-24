"""Set up Tollgate in a project, on this machine. It calls no outside service.

    python3 -m setup.init [--project .] [--replace]

The steps, in order:

1. Check that git, pre-commit, and claude are installed. With the
   isolation "container", the default, check that Docker is installed and running.
2. Check that the project is a git repository on the branch main.
3. Create the state folder.
4. Write .tollgate/settings.json, with the writing check.
5. Copy the checks into .tollgate/checks/ and write .pre-commit-config.yaml.
6. Commit these files on main, so the checks read the settings from main.
7. Run `pre-commit install`.

Running it again changes only what is missing. It prints one line for each step.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from gate import settings as st
from gate import state
from setup import install_writing_check, precommit

TOOLS = ("git", "pre-commit", "claude")
HARNESS = [".tollgate/checks/**", precommit.CONFIG]
SUBJECT = "chore(tollgate): set up Tollgate"


class InitError(RuntimeError):
    pass


def git(root, *args, check=True) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if check and proc.returncode:
        raise InitError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def check_tools(which=shutil.which) -> None:
    missing = [t for t in TOOLS if not which(t)]
    if missing:
        raise InitError(f"not installed: {', '.join(missing)}. Install them, then run again.")


def docker_ready(which=shutil.which) -> str:
    """Why Docker cannot run the builder, or "" when it can."""
    fix = 'Start Docker, or set "isolation": "sandbox" in .tollgate/settings.json.'
    if not which("docker"):
        return ("the isolation is container, so the builder runs in Docker, but docker is not "
                "installed. Install Docker, or set \"isolation\": \"sandbox\" in "
                ".tollgate/settings.json.")
    try:
        up = subprocess.run(["docker", "info"], capture_output=True, check=False,
                            timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        up = False
    return "" if up else f"docker is installed but not running. {fix}"


def check_isolation(root: Path, which=shutil.which) -> str:
    """Refuse the container isolation of the background driver when Docker cannot run.
    Session mode uses no isolation of the driver's, so it needs no Docker. Return one line."""
    path = root / st.PATH
    settings = json.loads(path.read_text()) if path.exists() else {}
    if settings.get("runner", "session") != "background":
        return "runner: session, Docker not needed"
    isolation = settings.get("isolation", "container")
    if isolation != "container":
        return f"isolation: {isolation}, Docker not needed"
    problem = docker_ready(which)
    if problem:
        raise InitError(problem)
    return "isolation: container, Docker is running"


def write_settings(root: Path) -> bool:
    """Add the harness to the settings. Return True when the file changed."""
    path = root / st.PATH
    settings = json.loads(path.read_text()) if path.exists() else {}
    before = json.dumps(settings, sort_keys=True)
    settings.setdefault("isolation", "container")
    harness = settings.setdefault("harness", [])
    harness += [h for h in HARNESS if h not in harness]
    if json.dumps(settings, sort_keys=True) == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return True


def test_check(root: Path) -> dict | None:
    """The gate's test check for the test suite init finds, or None. It knows a
    Python suite: test_*.py files under tests/ or test/, run with pytest. The gate
    reads the JUnit report the check writes."""
    for folder in ("tests", "test"):
        if any(Path(root, folder).rglob("test_*.py")):
            return {"run": f"python3 -m pytest -q -p no:cacheprovider "
                           f"--junitxml=report.xml {folder}", "report": "report.xml"}
    return None


def add_test_check(root: Path) -> str:
    """Write the test check when the settings have none. Return init's line for it."""
    path = root / st.PATH
    settings = json.loads(path.read_text())
    checks = settings.setdefault("checks", {})
    if "tests" in checks:
        return f"tests: {checks['tests'].get('run', '')}"
    found = test_check(root)
    if not found:
        return ("tests: no test suite found. Add a check named \"tests\" to \"checks\" in "
                f"{st.PATH}, a command that writes a JUnit report, and set \"report\" to its "
                "file. Until then the gate runs no tests.")
    checks["tests"] = found
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return f"tests: {found['run']}"


def init(project=".", replace=False, which=shutil.which, install=True) -> list:
    """Run every step. Return one line for each step."""
    root = Path(project).resolve()
    out = []
    check_tools(which)
    out.append(f"tools: {', '.join(TOOLS)} are installed")
    out.append(check_isolation(root, which))
    if git(root, "rev-parse", "--show-toplevel", check=False) != str(root):
        raise InitError(f"{root} is not the top folder of a git repository")
    branch = git(root, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    if branch != "main":
        raise InitError(f"the branch is {branch or 'detached'}, not main. Run: git switch main")
    for kind in state.KINDS:
        state.path(str(root), kind)
    out.append(f"state folder: {state.state_dir(str(root))}")
    changed = install_writing_check.install(str(root))
    if write_settings(root):
        changed.append(st.PATH)
    before = (root / st.PATH).read_text()
    tests_line = add_test_check(root)
    if (root / st.PATH).read_text() != before:
        changed.append(st.PATH)
    changed += precommit.write(str(root), replace)
    changed = sorted(set(changed))
    out.append(f"files: {', '.join(changed) if changed else 'already in place'}")
    out.append(tests_line)
    paths = [st.PATH, precommit.CHECKS_DIR, precommit.CONFIG]
    git(root, "add", "--", *paths)
    if git(root, "diff", "--cached", "--name-only", "--", *paths):
        # You run init, so this commit is yours. --no-verify: the locked-file check
        # would refuse a commit that changes .tollgate/.
        git(root, "commit", "-q", "--no-verify", "-m", SUBJECT, "--", *paths)
        out.append(f"commit: {git(root, 'rev-parse', '--short', 'HEAD')} {SUBJECT}")
    if install:
        proc = subprocess.run(["pre-commit", "install"], cwd=root, capture_output=True,
                              text=True, check=False)
        if proc.returncode:
            raise InitError(f"pre-commit install: {(proc.stderr or proc.stdout).strip()}")
        out.append(f"pre-commit: installed for {', '.join(precommit.HOOK_TYPES)}")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="init", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--replace", action="store_true",
                        help="replace a pre-commit config that Tollgate did not write")
    args = parser.parse_args(argv)
    try:
        for line in init(args.project, args.replace):
            print(line)
    except (InitError, precommit.PrecommitError, st.SettingsError, OSError) as err:
        print(f"init: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
