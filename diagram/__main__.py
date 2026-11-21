"""python3 -m diagram build <folder> [--check]: draw every spec in <folder>/src/."""

import argparse
import json
import sys
from pathlib import Path

from diagram import draw


def build(folder: str, check: bool = False, extra: dict | None = None) -> list:
    """Draw <folder>/src/*.json as <folder>/<name>.svg and <name>-dark.svg.

    `extra` maps more names to functions of a theme that return SVG text.
    Return the files that changed, or with check, that would.
    """
    base = Path(folder)
    makers = {}
    for src in sorted((base / "src").glob("*.json")):
        spec = json.loads(src.read_text())
        makers[src.stem] = lambda theme, spec=spec: draw(spec, theme)
    makers.update(extra or {})
    stale = []
    for name, make in makers.items():
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            target = base / f"{name}{suffix}.svg"
            text = make(theme)
            if not target.exists() or target.read_text() != text:
                stale.append(target.name)
                if not check:
                    target.write_text(text)
    return stale


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m diagram", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="draw every spec in <folder>/src/")
    b.add_argument("folder")
    b.add_argument("--check", action="store_true", help="change nothing; end with 1 if stale")
    args = parser.parse_args(argv)
    stale = build(args.folder, args.check)
    for name in stale:
        print(("out of date: " if args.check else "drew ") + name)
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
