"""Draw the project's diagrams as SVG, one light and one dark file for each.

    python3 docs/diagrams/build.py          # draw every spec in docs/diagrams/src/
    python3 docs/diagrams/build.py --check  # end with 1 if a drawn file is out of date

A spec is a JSON file in docs/diagrams/src/<name>.json:

    {"title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "nodes": [{"id": "a", "text": "First line\\nSecond line", "col": 0, "row": 0,
                "shape": "box" | "decision" | "note"}],
     "edges": [{"from": "a", "to": "b", "label": "optional", "dashed": false,
                "loop": "above" | "below" | "left" | "right", "reach": 120}]}

Nodes sit on a grid of columns and rows. An edge with "loop" is drawn as a curve
out to that side, so a loop reads as a loop. "reach" sets how far out it goes. Other edges are straight. The output is plain,
readable SVG: real text, a viewBox, role="img" with a title and a description
named by aria-labelledby, no scripts, and no external files.
"""

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
SIZE, LINE, PAD, GAP_X, GAP_Y, CHAR = 14, 19, 14, 70, 56, 7.4

# Text 4.5:1 or more on its fill, lines 3:1 or more on the page, in both themes.
THEMES = {
    "light": {"page": "#ffffff", "box": "#f6f8fa", "edge": "#57606a", "text": "#1f2328",
              "line": "#57606a", "decision": "#fff8c5", "note": "#ddf4ff", "label": "#1f2328"},
    "dark": {"page": "#0d1117", "box": "#161b22", "edge": "#8b949e", "text": "#e6edf3",
             "line": "#8b949e", "decision": "#3b2e00", "note": "#0c2d6b", "label": "#e6edf3"},
}


def size_of(node):
    lines = node["text"].split("\n")
    w = max(len(s) for s in lines) * CHAR + 2 * PAD
    h = len(lines) * LINE + 2 * PAD - (LINE - SIZE)
    if node.get("shape") == "decision":
        w, h = w * 1.35, h * 1.5
    return w, h


def layout(spec):
    # A gap must fit the widest label of a straight edge that crosses it.
    where = {n["id"]: (n["col"], n["row"]) for n in spec["nodes"]}
    gap_x, gap_y = GAP_X, GAP_Y
    for e in spec.get("edges", []):
        if e.get("label") and not e.get("loop"):
            (c1, r1), (c2, r2) = where[e["from"]], where[e["to"]]
            need = len(e["label"]) * CHAR * 0.92 + 50
            if r1 == r2:
                gap_x = max(gap_x, need)
            elif c1 == c2:
                gap_y = max(gap_y, 64)
    cols, rows = {}, {}
    for n in spec["nodes"]:
        w, h = size_of(n)
        cols[n["col"]] = max(cols.get(n["col"], 0), w)
        rows[n["row"]] = max(rows.get(n["row"], 0), h)
    x, xs = 24, {}
    for c in sorted(cols):
        xs[c] = x
        x += cols[c] + gap_x
    y, ys = 24, {}
    for r in sorted(rows):
        ys[r] = y
        y += rows[r] + gap_y
    boxes = {}
    for n in spec["nodes"]:
        w, h = size_of(n)
        cx = xs[n["col"]] + cols[n["col"]] / 2
        cy = ys[n["row"]] + rows[n["row"]] / 2
        boxes[n["id"]] = (cx, cy, w, h)
    width = x - gap_x + 24
    height = y - gap_y + 24
    return boxes, width, height


def edge_point(box, toward):
    """Where the line from the box's centre toward a point leaves the box."""
    cx, cy, w, h = box
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2) / abs(dx) if dx else float("inf")
    sy = (h / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def draw(spec, theme):
    t = THEMES[theme]
    boxes, width, height = layout(spec)
    seen = [(0, 0), (width, height)]
    out = [(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'width="{width:.0f}" height="{height:.0f}" role="img" '
            f'aria-labelledby="title desc" font-family="{FONT}" font-size="{SIZE}">'),
           f'<title id="title">{escape(spec["title"])}</title>',
           f'<desc id="desc">{escape(spec["desc"])}</desc>',
           ('<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
            f'markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{t["edge"]}"/></marker></defs>'),
           f'<rect width="100%" height="100%" fill="{t["page"]}"/>']
    for e in spec.get("edges", []):
        a, b = boxes[e["from"]], boxes[e["to"]]
        loop = e.get("loop")
        dash = ' stroke-dasharray="6 5"' if e.get("dashed") else ""
        if loop:
            # A loop arcs out to one side, so it reads as going back.
            side = {"above": (0, -1), "below": (0, 1), "left": (-1, 0), "right": (1, 0)}[loop]
            p1 = (a[0] + side[0] * a[2] / 2, a[1] + side[1] * a[3] / 2)
            p2 = (b[0] + side[0] * b[2] / 2, b[1] + side[1] * b[3] / 2)
            reach = e.get("reach", 44 + 0.12 * (abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])))
            c = ((p1[0] + p2[0]) / 2 + side[0] * reach, (p1[1] + p2[1]) / 2 + side[1] * reach)
            out.append(f'<path d="M{p1[0]:.1f},{p1[1]:.1f} Q{c[0]:.1f},{c[1]:.1f} '
                       f'{p2[0]:.1f},{p2[1]:.1f}" fill="none" stroke="{t["edge"]}" '
                       f'stroke-width="1.6"{dash} marker-end="url(#arrow)"/>')
            mid = (0.25 * p1[0] + 0.5 * c[0] + 0.25 * p2[0],
                   0.25 * p1[1] + 0.5 * c[1] + 0.25 * p2[1])
            seen += [mid]
        else:
            p1 = edge_point(a, b[:2])
            p2 = edge_point(b, a[:2])
            out.append(f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" '
                       f'y2="{p2[1]:.1f}" stroke="{t["edge"]}" stroke-width="1.6"{dash} '
                       f'marker-end="url(#arrow)"/>')
            mid = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        if e.get("label"):
            w = len(e["label"]) * CHAR * 0.92 + 10
            seen += [(mid[0] - w / 2, mid[1] - 12), (mid[0] + w / 2, mid[1] + 12)]
            out.append(f'<rect x="{mid[0] - w / 2:.1f}" y="{mid[1] - 11:.1f}" width="{w:.1f}" '
                       f'height="20" rx="4" fill="{t["page"]}"/>')
            out.append(f'<text x="{mid[0]:.1f}" y="{mid[1] + 4:.1f}" text-anchor="middle" '
                       f'font-size="{SIZE - 1}" fill="{t["label"]}">{escape(e["label"])}</text>')
    for n in spec["nodes"]:
        cx, cy, w, h = boxes[n["id"]]
        shape = n.get("shape", "box")
        fill = t.get(shape, t["box"])
        if shape == "decision":
            out.append(f'<polygon points="{cx:.1f},{cy - h / 2:.1f} {cx + w / 2:.1f},{cy:.1f} '
                       f'{cx:.1f},{cy + h / 2:.1f} {cx - w / 2:.1f},{cy:.1f}" fill="{fill}" '
                       f'stroke="{t["line"]}" stroke-width="1.4"/>')
        else:
            out.append(f'<rect x="{cx - w / 2:.1f}" y="{cy - h / 2:.1f}" width="{w:.1f}" '
                       f'height="{h:.1f}" rx="8" fill="{fill}" stroke="{t["line"]}" '
                       f'stroke-width="1.4"/>')
        lines = n["text"].split("\n")
        top = cy - (len(lines) - 1) * LINE / 2 + SIZE / 3
        for i, s in enumerate(lines):
            weight = ' font-weight="600"' if i == 0 and len(lines) > 1 else ""
            out.append(f'<text x="{cx:.1f}" y="{top + i * LINE:.1f}" text-anchor="middle" '
                       f'fill="{t["text"]}"{weight}>{escape(s)}</text>')
    out.append("</svg>")
    # Fit the picture to everything drawn, loops and labels included.
    x0 = min(x for x, _ in seen) - 12
    y0 = min(y for _, y in seen) - 12
    x1 = max(x for x, _ in seen) + 12
    y1 = max(y for _, y in seen) + 12
    w, h = x1 - x0, y1 - y0
    out[0] = out[0].replace(f'viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" '
                            f'height="{height:.0f}"',
                            f'viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" width="{w:.0f}" '
                            f'height="{h:.0f}"')
    out[4] = (f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" '
              f'fill="{t["page"]}"/>')
    return "\n".join(out) + "\n"


def build(check=False) -> list:
    """Draw every spec. Return the files that changed, or with check, that would."""
    stale = []
    for src in sorted((HERE / "src").glob("*.json")):
        spec = json.loads(src.read_text())
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            target = HERE / f"{src.stem}{suffix}.svg"
            text = draw(spec, theme)
            if not target.exists() or target.read_text() != text:
                stale.append(target.name)
                if not check:
                    target.write_text(text)
    return stale


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
