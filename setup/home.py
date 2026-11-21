"""A home: one private repository that holds many projects as git submodules.

    python3 -m setup.home init [--remote owner/name]
    python3 -m setup.home add owner/name
    python3 -m setup.home list

`init` makes the current empty folder a home: home.json, rules/lenses/, and a
README. With --remote it refuses a public repository. `add` adds the project as a
submodule under projects/<name> and says whether it has Tollgate settings yet.
The home never weakens a project: each project keeps its own settings, and the
server reads them from the project.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from setup.gh import Gh, GhError

HOME_FILE = "home.json"
NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class HomeError(RuntimeError):
    pass


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def load(home) -> dict:
    path = Path(home, HOME_FILE)
    if not path.exists():
        raise HomeError(f"{home} is not a home: {HOME_FILE} is missing")
    return json.loads(path.read_text())


def init(home: str, remote: str | None = None, gh=None) -> str:
    root = Path(home)
    if remote:
        if not NAME.match(remote):
            raise HomeError(f"not an owner/name: {remote}")
        try:
            private = (gh or Gh()).get(f"repos/{remote}").get("private")
        except GhError as err:
            raise HomeError(f"cannot read {remote}: {err}") from None
        if not private:
            raise HomeError(f"{remote} is public. A home holds the list of your projects, so it "
                            "must be private.")
    if Path(root, HOME_FILE).exists():
        return "already a home"
    others = [p.name for p in root.iterdir() if p.name != ".git"]
    if others:
        raise HomeError(f"the folder is not empty: {', '.join(sorted(others)[:5])}")
    if not Path(root, ".git").exists():
        git(root, "init", "-q", "-b", "main")
    if remote:
        git(root, "remote", "add", "origin", f"https://github.com/{remote}.git")
    Path(root, HOME_FILE).write_text(json.dumps({"projects": []}, indent=2) + "\n")
    Path(root, "rules", "lenses").mkdir(parents=True)
    Path(root, "rules", "lenses", ".keep").write_text("")
    Path(root, "README.md").write_text(
        "# Home\n\nThis repository holds projects as git submodules under `projects/`, and the "
        "rules they share under `rules/`. `/tollgate:home sync` opens a pull request in each "
        "project with the shared rules.\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "home: start")
    return "created"


def add(home: str, name: str, url: str | None = None) -> dict:
    """Add a project. `url` is for tests; it defaults to the GitHub address."""
    if not NAME.match(name):
        raise HomeError(f"not an owner/name: {name}")
    data = load(home)
    short = name.split("/")[1]
    if any(p["name"] == name for p in data["projects"]):
        return {"name": name, "path": f"projects/{short}", "added": False,
                "has_settings": Path(home, "projects", short, ".tollgate/settings.json").exists()}
    git(home, "-c", "protocol.file.allow=always", "submodule", "add", "-q",
        url or f"https://github.com/{name}.git", f"projects/{short}")
    data["projects"].append({"name": name, "path": f"projects/{short}"})
    Path(home, HOME_FILE).write_text(json.dumps(data, indent=2) + "\n")
    git(home, "add", "-A")
    git(home, "commit", "-q", "-m", f"home: add {name}")
    return {"name": name, "path": f"projects/{short}", "added": True,
            "has_settings": Path(home, "projects", short, ".tollgate/settings.json").exists()}


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="home", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--remote")
    p_add = sub.add_parser("add")
    p_add.add_argument("name")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print(init(args.home, args.remote, gh))
        elif args.command == "add":
            print(json.dumps(add(args.home, args.name)))
        else:
            for p in load(args.home)["projects"]:
                found = Path(args.home, p["path"], ".tollgate/settings.json").exists()
                print(f"{p['name']}\t{p['path']}\t{'settings' if found else 'no settings'}")
    except (HomeError, subprocess.CalledProcessError) as err:
        print(f"home: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
