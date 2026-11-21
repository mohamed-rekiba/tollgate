"""Draw the project's diagrams as SVG, one light and one dark file for each.

    python3 docs/diagrams/build.py          # draw every spec in docs/diagrams/src/
    python3 docs/diagrams/build.py --check  # end with 1 if a drawn file is out of date

A spec is a JSON file in docs/diagrams/src/<name>.json:

    {"title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "nodes": [{"id": "a", "text": "Title\\nOne line under it", "col": 0, "row": 0,
                "kind": "you" | "ai" | "server" | "check" | "advisor",
                "step": 1, "tag": "OWN LABEL"}],
     "edges": [{"from": "a", "to": "b", "label": "optional",
                "tone": "pass" | "fail", "dashed": true,
                "loop": "left" | "right" | "above" | "below",
                "route": "vhv" | "vh" | "hv"}]}

The design:
- Nodes sit on a grid. All boxes in one diagram share one width.
- "kind" says who acts. It sets the color of the stripe and of the small label
  over the title (YOU, AI, SERVER, CHECK, ADVISOR), so the meaning is in words
  and in color. "step" adds STEP n to that label. "tag" replaces the label.
- Arrows are straight, or bend at right angles with round corners. "route"
  picks the bends for an arrow between two rows and two columns: "vhv" (the
  default) goes down, across, down; "vh" goes up or down, then across; "hv"
  goes across, then up or down.
- "loop" draws an arrow that goes back, out to one side in its own lane, so
  loops never cross each other's labels.
- "tone" colors an arrow and its label: green for pass, red for fail.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
FONT = ("-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, "
        "sans-serif")

TITLE, SUB, EYEBROW, LABEL = 15, 13, 10.5, 12
PAD_X, PAD_Y, STRIPE, RADIUS = 18, 14, 4, 10
MIN_W, GAP_X, GAP_Y, MARGIN = 170, 48, 40, 22
KIND_NAMES = {"you": "YOU", "ai": "AI", "server": "SERVER", "check": "CHECK",
              "advisor": "ADVISOR"}

# Every pair passes WCAG 2.1: text 4.5 to 1 on its fill, lines 3 to 1 on the page.
# tests/test_diagrams.py checks this.
THEMES = {
    "light": {
        "page": "#ffffff", "frame": "#d1d9e0", "box": "#ffffff", "border": "#d1d9e0",
        "text": "#1f2328", "sub": "#59636e", "edge": "#818b98", "shadow": 0.07,
        "kinds": {"you": ("#0969da", "#f3f8ff"), "ai": ("#8250df", "#f9f6ff"),
                  "server": ("#1a7f37", "#f2fbf4"), "check": ("#9a6700", "#fff9e5"),
                  "advisor": ("#bc4c00", "#fff5ee")},
        "tones": {"fail": "#cf222e", "pass": "#1a7f37"},
    },
    "dark": {
        "page": "#0d1117", "frame": "#30363d", "box": "#151b23", "border": "#3d444d",
        "text": "#f0f6fc", "sub": "#9198a1", "edge": "#656c76", "shadow": 0,
        "kinds": {"you": ("#4493f8", "#0d1d35"), "ai": ("#ab7df8", "#1b1430"),
                  "server": ("#3fb950", "#0c2114"), "check": ("#d29922", "#221a08"),
                  "advisor": ("#f0883e", "#271608")},
        "tones": {"fail": "#f85149", "pass": "#3fb950"},
    },
}


def text_width(s, size, bold=False, caps=False):
    """A close guess of how wide a line of the system sans font is."""
    per = 0.6 if bold else 0.55
    if caps:
        return len(s) * (size * 0.68 + 0.9)
    return sum(size * (0.3 if c in "il.,:'| " else per) for c in s)


def eyebrow(node):
    if node.get("tag"):
        return node["tag"]
    name = KIND_NAMES.get(node.get("kind"), "")
    if node.get("step") is not None:
        return f"STEP {node['step']}" + (f" · {name}" if name else "")
    return name


def node_size(node):
    title, *sub = node["text"].split("\n")
    widths = [text_width(title, TITLE, bold=True)] + [text_width(s, SUB) for s in sub]
    if eyebrow(node):
        widths.append(text_width(eyebrow(node), EYEBROW, caps=True))
    w = max(widths) + 2 * PAD_X + STRIPE
    h = 2 * PAD_Y + 18 + 18 * len(sub) + (16 if eyebrow(node) else 0)
    return w, h


def label_size(label):
    return text_width(label, LABEL) + 16, 22


def layout(spec):
    nodes = spec["nodes"]
    width = max(MIN_W, *(node_size(n)[0] for n in nodes))
    where = {n["id"]: (n["col"], n["row"]) for n in nodes}
    gap_x, gap_y = GAP_X, GAP_Y
    for e in spec.get("edges", []):
        if not e.get("label") or e.get("loop"):
            continue
        r1, r2 = where[e["from"]][1], where[e["to"]][1]
        lw, lh = label_size(e["label"])
        if r1 == r2:
            gap_x = max(gap_x, lw + 28)
        else:
            gap_y = max(gap_y, lh + 30)
    heights = {}
    for n in nodes:
        heights[n["row"]] = max(heights.get(n["row"], 0), node_size(n)[1])
    ys, y = {}, 0
    for r in sorted(heights):
        ys[r] = y
        y += heights[r] + gap_y
    boxes = {}
    for n in nodes:
        left = n["col"] * (width + gap_x)
        boxes[n["id"]] = {"l": left, "t": ys[n["row"]], "r": left + width,
                          "b": ys[n["row"]] + heights[n["row"]],
                          "x": left + width / 2, "y": ys[n["row"]] + heights[n["row"]] / 2}
    return boxes


def rounded(points, radius=12):
    """An SVG path through the points, with round corners."""
    d = f"M{points[0][0]:.1f},{points[0][1]:.1f}"
    for i in range(1, len(points) - 1):
        (x0, y0), (x1, y1), (x2, y2) = points[i - 1], points[i], points[i + 1]
        r = min(radius, abs(x1 - x0 + y1 - y0) / 2, abs(x2 - x1 + y2 - y1) / 2)
        ax = x1 - r * ((x1 > x0) - (x1 < x0))
        ay = y1 - r * ((y1 > y0) - (y1 < y0))
        bx = x1 + r * ((x2 > x1) - (x2 < x1))
        by = y1 + r * ((y2 > y1) - (y2 < y1))
        d += f" L{ax:.1f},{ay:.1f} Q{x1:.1f},{y1:.1f} {bx:.1f},{by:.1f}"
    return d + f" L{points[-1][0]:.1f},{points[-1][1]:.1f}"


def loop_lanes(spec, boxes):
    """Give each loop its own distance from the boxes, inner loops first."""
    rows = {n["id"]: n["row"] for n in spec["nodes"]}
    cols = {n["id"]: n["col"] for n in spec["nodes"]}
    lanes = {}
    for side in ("left", "right", "above", "below"):
        loops = [e for e in spec.get("edges", []) if e.get("loop") == side]
        across = side in ("left", "right")

        def span(e, across=across):
            a, b = boxes[e["from"]], boxes[e["to"]]
            return abs(a["y"] - b["y"]) if across else abs(a["x"] - b["x"])

        offset, last = 0, 0
        for e in sorted(loops, key=span):
            half = (label_size(e["label"])[0 if across else 1] / 2) if e.get("label") else 4
            offset = (half + 22) if not offset else offset + last + half + 14
            last = half
            if across:
                lo, hi = sorted((rows[e["from"]], rows[e["to"]]))
                near = [boxes[n] for n in rows if lo <= rows[n] <= hi]
                base = min(b["l"] for b in near) if side == "left" else max(b["r"] for b in near)
            else:
                lo, hi = sorted((cols[e["from"]], cols[e["to"]]))
                near = [boxes[n] for n in cols if lo <= cols[n] <= hi]
                base = min(b["t"] for b in near) if side == "above" else max(b["b"] for b in near)
            lanes[id(e)] = base - offset if side in ("left", "above") else base + offset
    return lanes


def route(e, boxes, lanes):
    """The points of one arrow, and where its label goes."""
    a, b = boxes[e["from"]], boxes[e["to"]]
    side = e.get("loop")
    if side in ("left", "right"):
        x = lanes[id(e)]
        sa, sb = (a["l"], b["l"]) if side == "left" else (a["r"], b["r"])
        pts = [(sa, a["y"]), (x, a["y"]), (x, b["y"]), (sb, b["y"])]
        return pts, (x, (a["y"] + b["y"]) / 2)
    if side in ("above", "below"):
        y = lanes[id(e)]
        sa, sb = (a["t"], b["t"]) if side == "above" else (a["b"], b["b"])
        pts = [(a["x"], sa), (a["x"], y), (b["x"], y), (b["x"], sb)]
        return pts, ((a["x"] + b["x"]) / 2, y)
    if abs(a["y"] - b["y"]) < 1:
        sa, sb = (a["r"], b["l"]) if b["x"] > a["x"] else (a["l"], b["r"])
        return [(sa, a["y"]), (sb, b["y"])], ((sa + sb) / 2, a["y"])
    down = b["y"] > a["y"]
    if abs(a["x"] - b["x"]) < 1:
        sa, sb = (a["b"], b["t"]) if down else (a["t"], b["b"])
        return [(a["x"], sa), (b["x"], sb)], (a["x"], (sa + sb) / 2)
    kind = e.get("route", "vhv")
    right = b["x"] > a["x"]
    if kind == "vh":
        sa = a["b"] if down else a["t"]
        sb = b["l"] if right else b["r"]
        pts = [(a["x"], sa), (a["x"], b["y"]), (sb, b["y"])]
        return pts, (a["x"], (sa + b["y"]) / 2)
    if kind == "hv":
        sa = a["r"] if right else a["l"]
        sb = b["t"] if down else b["b"]
        pts = [(sa, a["y"]), (b["x"], a["y"]), (b["x"], sb)]
        return pts, ((sa + b["x"]) / 2, a["y"])
    sa, sb = (a["b"], b["t"]) if down else (a["t"], b["b"])
    mid = (sa + sb) / 2
    pts = [(a["x"], sa), (a["x"], mid), (b["x"], mid), (b["x"], sb)]
    return pts, (b["x"], (mid + sb) / 2)


def draw(spec, theme):
    t = THEMES[theme]
    boxes = layout(spec)
    lanes = loop_lanes(spec, boxes)
    body, seen = [], []
    for bx in boxes.values():
        seen += [(bx["l"], bx["t"]), (bx["r"], bx["b"])]

    edges, labels = [], []
    for e in spec.get("edges", []):
        pts, mid = route(e, boxes, lanes)
        seen += pts
        tone = e.get("tone")
        color = t["tones"].get(tone, t["edge"])
        marker = f"arrow-{tone or 'plain'}"
        dash = ' stroke-dasharray="5 5"' if e.get("dashed") else ""
        edges.append(f'<path d="{rounded(pts)}" fill="none" stroke="{color}" stroke-width="1.6" '
                     f'stroke-linecap="round" stroke-linejoin="round"{dash} '
                     f'marker-end="url(#{marker})"/>')
        if e.get("label"):
            w, h = label_size(e["label"])
            ink = t["tones"].get(tone, t["sub"])
            frame = t["tones"].get(tone, t["border"])
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
            labels.append(f'<rect x="{mid[0] - w / 2:.1f}" y="{mid[1] - h / 2:.1f}" width="{w:.1f}" '
                          f'height="{h}" rx="{h / 2}" fill="{t["page"]}" stroke="{frame}" '
                          f'stroke-width="1"/>')
            labels.append(f'<text x="{mid[0]:.1f}" y="{mid[1] + 4.2:.1f}" text-anchor="middle" '
                          f'font-size="{LABEL}" font-weight="500" fill="{ink}">'
                          f'{escape(e["label"])}</text>')

    for i, n in enumerate(spec["nodes"]):
        bx = boxes[n["id"]]
        kind = n.get("kind")
        accent, tint = t["kinds"].get(kind, (None, t["box"]))
        w, h = bx["r"] - bx["l"], bx["b"] - bx["t"]
        shadow = ' filter="url(#shadow)"' if t["shadow"] else ""
        body.append(f'<rect x="{bx["l"]:.1f}" y="{bx["t"]:.1f}" width="{w:.1f}" height="{h:.1f}" '
                    f'rx="{RADIUS}" fill="{tint}" stroke="{accent or t["border"]}" '
                    f'stroke-opacity="{0.55 if accent else 1}" stroke-width="1"{shadow}/>')
        if accent:
            body.append(f'<clipPath id="clip{i}"><rect x="{bx["l"]:.1f}" y="{bx["t"]:.1f}" '
                        f'width="{w:.1f}" height="{h:.1f}" rx="{RADIUS}"/></clipPath>')
            body.append(f'<rect x="{bx["l"]:.1f}" y="{bx["t"]:.1f}" width="{STRIPE}" '
                        f'height="{h:.1f}" fill="{accent}" clip-path="url(#clip{i})"/>')
        x = bx["l"] + STRIPE + PAD_X
        y = bx["t"] + PAD_Y
        brow = eyebrow(n)
        if brow:
            body.append(f'<text x="{x:.1f}" y="{y + 10:.1f}" font-size="{EYEBROW}" '
                        f'font-weight="700" letter-spacing="0.9" fill="{accent or t["sub"]}">'
                        f'{escape(brow)}</text>')
            y += 16
        title, *sub = n["text"].split("\n")
        body.append(f'<text x="{x:.1f}" y="{y + 14:.1f}" font-size="{TITLE}" font-weight="600" '
                    f'fill="{t["text"]}">{escape(title)}</text>')
        for j, s in enumerate(sub):
            body.append(f'<text x="{x:.1f}" y="{y + 33 + 18 * j:.1f}" font-size="{SUB}" '
                        f'fill="{t["sub"]}">{escape(s)}</text>')

    x0 = min(p[0] for p in seen) - MARGIN
    y0 = min(p[1] for p in seen) - MARGIN
    x1 = max(p[0] for p in seen) + MARGIN
    y1 = max(p[1] for p in seen) + MARGIN
    w, h = x1 - x0, y1 - y0
    markers = []
    for name, color in [("plain", t["edge"])] + list(t["tones"].items()):
        markers.append(f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                       f'markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" '
                       f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9 L3.2,5 z" '
                       f'fill="{color}"/></marker>')
    shadow = (f'<filter id="shadow" x="-10%" y="-10%" width="120%" height="140%">'
              f'<feDropShadow dx="0" dy="1" stdDeviation="1.6" flood-color="#1f2328" '
              f'flood-opacity="{t["shadow"]}"/></filter>') if t["shadow"] else ""
    head = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" '
         f'width="{w:.0f}" height="{h:.0f}" role="img" aria-labelledby="title desc" '
         f'font-family="{FONT}">'),
        f'<title id="title">{escape(spec["title"])}</title>',
        f'<desc id="desc">{escape(spec["desc"])}</desc>',
        f'<defs>{"".join(markers)}{shadow}</defs>',
        (f'<rect x="{x0 + 0.5:.1f}" y="{y0 + 0.5:.1f}" width="{w - 1:.0f}" height="{h - 1:.0f}" '
         f'rx="12" fill="{t["page"]}" stroke="{t["frame"]}"/>'),
    ]
    return "\n".join(head + edges + body + labels + ["</svg>"]) + "\n"


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
