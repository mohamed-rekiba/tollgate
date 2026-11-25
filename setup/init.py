"""Set up Tollgate in a project, on this machine. It calls no outside service.

    python3 -m setup.init [--project .] [--replace] [--settings FILE]

The steps, in order:

1. Check that git, pre-commit, and claude are installed. With the
   isolation "container", the default, check that Docker is installed and running.
2. Check that the project is a git repository on the branch main.
3. Create the state folder.
4. Write .tollgate/settings.json, with the writing check. With --settings, FILE is a
   JSON draft of the settings, written outside the project. Init checks it, then writes it
   here, because the guard does not let your own session write under .tollgate/ except
   plans, tickets, roadmaps, and requests. If .tollgate/settings.json already exists and
   differs from the draft, init stops and leaves the file as it is.
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


def with_harness(settings: dict) -> dict:
    """The settings with the isolation default and the harness that init adds."""
    settings.setdefault("isolation", "container")
    harness = settings.setdefault("harness", [])
    harness += [h for h in HARNESS if h not in harness]
    return settings


def read_draft(file: str) -> dict:
    """The settings in a draft file. Raise InitError or SettingsError when it cannot be used."""
    try:
        text = Path(file).read_text()
    except OSError as err:
        raise InitError(f"cannot read the settings file {file}: {err}") from None
    st.parse(text)
    return json.loads(text)


def covers(existing: dict, draft: dict) -> bool:
    """True when the settings on disk hold everything in the draft. Init adds the harness, the
    writing check, and a test check, so the file may hold more than the draft."""
    for key, value in draft.items():
        have = existing.get(key)
        if key == "harness":
            if not all(item in (have or []) for item in value):
                return False
        elif key == "checks":
            if not all((have or {}).get(name) == check for name, check in value.items()):
                return False
        elif have != value:
            return False
    return True


def place_draft(root: Path, file: str) -> bool:
    """Write the draft as the project's settings. Return True when the file was written.
    It never replaces settings that differ: the user edits those."""
    draft = read_draft(file)
    path = root / st.PATH
    if path.exists():
        if covers(json.loads(path.read_text()), draft):
            return False
        raise InitError(f"{st.PATH} already exists and differs from {file}. Edit it yourself, "
                        "or delete it, then run init again.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(with_harness(draft), indent=2) + "\n")
    return True


def write_settings(root: Path) -> bool:
    """Add the harness to the settings. Return True when the file changed."""
    path = root / st.PATH
    settings = json.loads(path.read_text()) if path.exists() else {}
    before = json.dumps(settings, sort_keys=True)
    with_harness(settings)
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


def init(project=".", replace=False, which=shutil.which, install=True, settings_file=None) -> list:
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
    changed = []
    if settings_file and place_draft(root, settings_file):   # first: a bad draft changes no file
        changed.append(st.PATH)
    changed += install_writing_check.install(str(root))
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
    parser.add_argument("--settings", metavar="FILE",
                        help="a JSON draft of the settings, written outside the project; init "
                             "checks it and writes it as .tollgate/settings.json")
    args = parser.parse_args(argv)
    try:
        for line in init(args.project, args.replace, settings_file=args.settings):
            print(line)
    except (InitError, precommit.PrecommitError, st.SettingsError, OSError) as err:
        print(f"init: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
