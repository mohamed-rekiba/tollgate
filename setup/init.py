"""Set up Tollgate in a project, on this machine. It calls no outside service.

    python3 -m setup.init [--project .] [--owner-key ~/.ssh/id_ed25519.pub] [--replace]

The steps, in order:

1. Check that git, ssh-keygen, pre-commit, and claude are installed. With the
   isolation "container", the default, check that Docker is installed and running.
2. Check that the project is a git repository on the branch main.
3. Create the state folder, and this machine's key.
4. Add the machine's public key to `signers`, which sign locks and pass
   records, and your SSH public key to `owners`, who approve tier 3 and 4.
5. Write .tollgate/settings.json, with the writing check.
6. Copy the checks into .tollgate/checks/ and write .pre-commit-config.yaml.
7. Commit these files on main, so the checks read the signers from main.
8. Run `pre-commit install`.

Running it again changes only what is missing. It prints one line for each step.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from gate import settings as st
from gate import sign, state
from setup import install_writing_check, precommit

TOOLS = ("git", "ssh-keygen", "pre-commit", "claude")
OWNER_KEYS = ("id_ed25519.pub", "id_ecdsa.pub", "id_ed25519_sk.pub", "id_rsa.pub")
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
    """Refuse the container isolation when Docker cannot run. Return one line."""
    path = root / st.PATH
    settings = json.loads(path.read_text()) if path.exists() else {}
    isolation = settings.get("isolation", "container")
    if isolation != "container":
        return f"isolation: {isolation}, Docker not needed"
    problem = docker_ready(which)
    if problem:
        raise InitError(problem)
    return "isolation: container, Docker is running"


def owner_key(path: str | None = None) -> str:
    """Your SSH public key line. The default is the first key found in ~/.ssh/."""
    if path:
        candidates = [Path(path).expanduser()]
    else:
        candidates = [Path.home() / ".ssh" / name for name in OWNER_KEYS]
    for candidate in candidates:
        if candidate.exists():
            line = candidate.read_text().strip()
            if not line.startswith(("ssh-", "ecdsa-", "sk-")):
                raise InitError(f"{candidate} is not an SSH public key")
            return line
    raise InitError("no SSH public key found. Make one with: ssh-keygen -t ed25519")


def add_key(keys: list, line: str) -> None:
    if key_id(line) not in {key_id(k) for k in keys}:
        keys.append(line)


def write_settings(root: Path, machine: str, owner: str) -> bool:
    """Add the keys and the harness to the settings. Return True when the file changed."""
    path = root / st.PATH
    settings = json.loads(path.read_text()) if path.exists() else {}
    before = json.dumps(settings, sort_keys=True)
    add_key(settings.setdefault("signers", []), machine)
    add_key(settings.setdefault("owners", []), owner)
    settings.setdefault("isolation", "container")
    harness = settings.setdefault("harness", [])
    harness += [h for h in HARNESS if h not in harness]
    if json.dumps(settings, sort_keys=True) == before:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")
    return True


def key_id(line: str) -> str:
    return " ".join(line.split()[:2])


def init(project=".", key_path=None, replace=False, which=shutil.which, install=True) -> list:
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
    machine, owner = sign.ensure_key(), owner_key(key_path)
    if key_id(machine) == key_id(owner):
        raise InitError("your SSH key is the machine key. Name your own key with --owner-key.")
    out.append(f"machine key: {sign.machine_key()}")
    changed = install_writing_check.install(str(root))
    if write_settings(root, machine, owner):
        changed.append(st.PATH)
    changed += precommit.write(str(root), replace)
    changed = sorted(set(changed))
    out.append(f"files: {', '.join(changed) if changed else 'already in place'}")
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
    parser.add_argument("--owner-key", help="your SSH public key; the default is in ~/.ssh/")
    parser.add_argument("--replace", action="store_true",
                        help="replace a pre-commit config that Tollgate did not write")
    args = parser.parse_args(argv)
    try:
        for line in init(args.project, args.owner_key, args.replace):
            print(line)
    except (InitError, precommit.PrecommitError, st.SettingsError, sign.SignError,
            OSError) as err:
        print(f"init: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
