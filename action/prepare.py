"""Put back the harness from the main branch and the locked files from the freeze.

This runs in the checkout of a change, before its checks run. A change then
runs its tests with the main branch's test settings and with the locked tests
unchanged.
"""

import argparse
import sys
from pathlib import Path

from action import settings as st
from action.gitio import git, show_bytes
from action.paths import matches


def _tree(repo, ref) -> list:
    return git(repo, "ls-tree", "-r", "--name-only", ref).splitlines()


def restore(repo, base: str, freeze_commit: str | None = None, manifest=None,
            keep_harness: bool = False) -> list:
    """Return the paths it rewrote or removed."""
    repo = Path(repo)
    settings = st.load_from_ref(str(repo), base)
    touched = []
    if not keep_harness:
        on_disk = [str(p.relative_to(repo)) for p in repo.rglob("*")
                   if p.is_file() and ".git" not in p.relative_to(repo).parts]
        paths = {p for p in on_disk + _tree(repo, base) if matches(p, settings["harness"])}
        for path in sorted(paths):
            data = show_bytes(repo, base, path)
            target = repo / path
            if data is None:
                if target.exists():
                    target.unlink()
                    touched.append(path)
            elif not target.exists() or target.read_bytes() != data:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                touched.append(path)
    if manifest and freeze_commit:
        for path in manifest["files"]:
            if matches(path, settings["harness"]):
                continue  # the harness from the main branch wins
            data = show_bytes(repo, freeze_commit, path)
            target = repo / path
            if data is not None and (not target.exists() or target.read_bytes() != data):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                touched.append(path)
    return touched


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tollgate prepare", description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--ticket", help="put back the locked files of this ticket's freeze")
    parser.add_argument("--keep-harness", action="store_true")
    args = parser.parse_args(argv)
    freeze_commit = manifest = None
    if args.ticket:
        from action.gate import _freeze
        freeze = _freeze(args.repo, args.ticket)
        if freeze:
            freeze_commit, manifest = freeze.tag_commit, freeze.manifest
    for path in restore(args.repo, args.base, freeze_commit, manifest, args.keep_harness):
        print(f"put back: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
