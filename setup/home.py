"""A home: one git repository on your machine that holds many projects as git submodules.

    python3 -m setup.home init
    python3 -m setup.home add <path or git address> [--name <name>]
    python3 -m setup.home list

`init` makes the current empty folder a home: home.json, rules/lenses/, and a
README. `add` adds a project as a submodule under projects/<name> and says
whether it has Tollgate settings yet. The home does not track which commit a
project is on, so a project's own commits never show the home as changed. The home never weakens a project: each
project keeps its own settings, and the gate reads them from the project's main.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HOME_FILE = "home.json"
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


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


def init(home: str) -> str:
    root = Path(home)
    if Path(root, HOME_FILE).exists():
        return "already a home"
    others = [p.name for p in root.iterdir() if p.name != ".git"]
    if others:
        raise HomeError(f"the folder is not empty: {', '.join(sorted(others)[:5])}")
    if not Path(root, ".git").exists():
        git(root, "init", "-q", "-b", "main")
    Path(root, HOME_FILE).write_text(json.dumps({"projects": []}, indent=2) + "\n")
    Path(root, "rules", "lenses").mkdir(parents=True)
    Path(root, "rules", "lenses", ".keep").write_text("")
    Path(root, "README.md").write_text(
        "# Home\n\nThis repository holds projects as git submodules under `projects/`, and the "
        "rules they share under `rules/`. `/tollgate:home sync` puts the shared rules in each "
        "project as a ready change, and you merge each one with `/tollgate:merge`.\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "chore(home): start")
    return "created"


def add(home: str, source: str, name: str | None = None) -> dict:
    """Add a project from a folder or a git address."""
    data = load(home)
    name = name or Path(source.rstrip("/")).name.removesuffix(".git")
    if not NAME.match(name):
        raise HomeError(f"not a name for a folder: {name}")
    path = f"projects/{name}"
    added = not any(p["path"] == path for p in data["projects"])
    if added:
        url = str(Path(source).resolve()) if Path(source).exists() else source
        git(home, "-c", "protocol.file.allow=always", "submodule", "add", "-q", url, path)
        # A home groups projects; it does not pin them. Without this, each new
        # commit in a project shows the home as changed.
        git(home, "config", "-f", ".gitmodules", f"submodule.{path}.ignore", "all")
        data["projects"].append({"name": name, "path": path})
        Path(home, HOME_FILE).write_text(json.dumps(data, indent=2) + "\n")
        git(home, "add", "-A")
        git(home, "commit", "-q", "-m", f"chore(home): add {name}")
    return {"name": name, "path": path, "added": added,
            "has_settings": Path(home, path, ".tollgate/settings.json").exists()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="home", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=".")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p_add = sub.add_parser("add")
    p_add.add_argument("source")
    p_add.add_argument("--name")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            print(init(args.home))
        elif args.command == "add":
            print(json.dumps(add(args.home, args.source, args.name)))
        else:
            for p in load(args.home)["projects"]:
                print(f"{p['name']}\t{p['path']}")
    except (HomeError, subprocess.CalledProcessError) as err:
        print(f"home: {getattr(err, 'stderr', None) or err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
