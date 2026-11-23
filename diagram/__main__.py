"""python3 -m diagram build <folder> [--check]: draw every spec in <folder>/src/.

A spec with "from" draws another spec of the same folder, with its own keys on
top: {"from": "c4-container.json", "style": "isometric"} draws the container
diagram again, as an isometric scene, and follows every change to it.
"""

import argparse
import json
import sys
from pathlib import Path

from diagram import aws, draw


def build(folder: str, check: bool = False, extra: dict | None = None) -> list:
    """Draw <folder>/src/*.json as <folder>/<name>.svg and <name>-dark.svg.

    `extra` maps more names to functions of a theme that return SVG text.
    Return the files that changed, or with check, that would.
    """
    base = Path(folder)
    specs = sorted((base / "src").glob("*.json"))
    if not specs and not extra:
        raise SystemExit(f"No specs in {base / 'src'}. Each diagram is <folder>/src/<name>.json.")
    makers = {}
    for src in specs:
        spec = json.loads(src.read_text())
        if "from" in spec:
            base_file = base / "src" / spec["from"]
            if not base_file.is_file():
                raise ValueError(f"{src.name} draws from {spec['from']}, which is not in "
                                 f"{base / 'src'}")
            spec = json.loads(base_file.read_text()) | {k: v for k, v in spec.items()
                                                        if k != "from"}
        makers[src.stem] = lambda theme, spec=spec: draw(spec, theme)
    makers.update(extra or {})
    stale = []
    # A drawing whose spec is gone is stale too.
    for svg in base.glob("*.svg"):
        name = svg.stem.removesuffix("-dark")
        if name not in makers:
            stale.append(f"{svg.name} (no spec)")
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
    try:
        stale = build(args.folder, args.check)
    except (aws.Missing, ValueError, KeyError) as err:
        # A person reads this: the message, not a traceback.
        print(f"Cannot draw the diagrams: {err}", file=sys.stderr)
        return 2
    for name in stale:
        print(("out of date: " if args.check else "drew ") + name)
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
