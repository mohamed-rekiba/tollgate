"""Draw the project's diagrams as SVG, one light and one dark file for each.

    python3 docs/diagrams/build.py          # draw every diagram
    python3 docs/diagrams/build.py --check  # end with 1 if a drawn file is out of date

Two kinds of diagram:
- Written: a spec in docs/diagrams/src/<name>.json, a flow or a scene. The
  formats are in diagram/__init__.py and diagram/flow.py.
- Art: a picture drawn in its own code, such as the README banner in hero.py.
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import hero

from diagram.__main__ import build as build_folder
from diagram.flow import MONO, THEMES

__all__ = ["THEMES", "build"]

def icons_sheet(theme: str) -> str:
    """Every icon in diagram/icons.py, large, with its name: a reference for writers."""
    from xml.sax.saxutils import escape

    from diagram.icons import ICONS, icon
    c = THEMES[theme]
    # Each icon in the color of its family: who acts in their own colors, then
    # the work, the code, the places, and the signals.
    family = {"person": "you", "ai": "ai", "server": "server", "check": "check",
              "advisor": "advisor", "lock": "server", "gate": "check", "test": "check",
              "plan": "ai", "ticket": "ai", "retry": "ai", "workflow": "ai", "branch": "server",
              "pull-request": "server", "merge": "server", "home": "you", "folder": "you",
              "package": "you", "terminal": "you", "cost": "advisor", "warning": "advisor",
              "clock": "advisor", "retro": "advisor",
              # Architecture: data and compute green, network and devices blue, code purple,
              # guards amber, signals orange.
              "database": "server", "bucket": "server", "cache": "server", "queue": "server",
              "container": "server", "cluster": "server", "function": "ai", "chip": "server",
              "cloud": "you", "globe": "you", "load-balancer": "server", "firewall": "check",
              "api": "ai", "users": "you", "browser": "you", "phone": "you", "laptop": "you",
              "key": "check", "monitor": "check", "search": "check", "event": "advisor",
              "bell": "advisor", "mail": "advisor", "settings": "ai", "code": "ai"}
    per_row, cw, ch, pad = 6, 128, 112, 24
    rows = -(-len(ICONS) // per_row)
    w, h = per_row * cw + 2 * pad, rows * ch + 2 * pad
    out = [(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" '
           f'height="{h}" role="img" aria-labelledby="title desc" font-family="{MONO}">'),
           "<title id=\"title\">Tollgate's icons</title>",
           (f'<desc id="desc">Every icon in diagram/icons.py, with its name: '
           f'{escape(", ".join(ICONS))}.</desc>'),
           f'<rect width="{w}" height="{h}" fill="{c["page"]}"/>']
    for i, name in enumerate(ICONS):
        x, y = pad + (i % per_row) * cw, pad + (i // per_row) * ch
        accent, tint = c["kinds"][family.get(name, "neutral")]
        out.append(f'<rect x="{x + 6}" y="{y + 6}" width="{cw - 12}" height="{ch - 12}" rx="6" '
                   f'fill="{tint}" stroke="{accent}" stroke-opacity="0.6"/>')
        out.append(icon(name, x + cw / 2 - 20, y + 22, 40, accent, 2))
        out.append(f'<text x="{x + cw / 2}" y="{y + 86}" text-anchor="middle" font-size="12" '
                   f'fill="{c["sub"]}">{escape(name)}</text>')
    return "\n".join([*out, "</svg>"]) + "\n"


# Drawn by hand in code, not from a spec.
ART = {"hero": hero.draw, "icons": icons_sheet}


def build(check=False) -> list:
    """Draw every diagram: the specs in src/ and the art."""
    return build_folder(str(HERE), check, dict(ART))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="change nothing; end with 1 if stale")
    args = parser.parse_args(argv)
    stale = build(args.check)
    for name in stale:
        print(("out of date: " if args.check else "drew ") + name)
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
