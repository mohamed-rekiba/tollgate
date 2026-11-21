"""Draw a diagram as SVG, in a light and a dark theme: the flat blueprint style.

    from driver.diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "nodes": [{"id": "a", "text": "Title\\nOne line under it", "col": 0, "row": 0,
                "kind": "you" | "ai" | "server" | "check" | "advisor",
                "icon": "lock", "tag": "OWN LABEL", "step": 1,
                "aws": "s3"}],
     "edges": [{"from": "a", "to": "b", "label": "optional",
                "tone": "pass" | "fail", "dashed": true,
                "loop": "left" | "right" | "above" | "below",
                "route": "vhv" | "vh" | "hv"}],
     "groups": [{"label": "The server", "nodes": ["a", "b"], "kind": "server",
                 "icon": "lock", "aws": "vpc"}],
     "ticket": {"path": [["a", "b"], ["b", "c"]], "wait": {"b": 1.2}}}

The design:
- A fine grid behind everything, monospace type, square tags.
- Nodes sit on a grid of columns and rows. All boxes share one width.
- "kind" says who acts. It sets the color, the icon, and the small label over
  the title (YOU, AI, SERVER, CHECK, ADVISOR). "icon" picks another icon from
  driver/icons.py. "step" adds STEP n. "tag" replaces the label. A box with
  no kind is neutral slate.
- "aws" draws the official AWS service icon with its name under it, the way
  AWS diagrams do. The icons come from a local copy of the AWS package; see
  driver/aws.py.
- "groups" draw a border around nodes: a place, a boundary, or an AWS group
  ("aws": "cloud", "region", "az", "vpc", "public subnet", "private subnet",
  "security group", ...), in AWS's own color with its group icon. Groups may
  nest; inner ones must hold a subset of the outer one's nodes.
- Arrows are straight, or bend at right angles with round corners. "route"
  picks the bends for an arrow between two rows and two columns: "vhv" (the
  default) goes down, across, down; "vh" goes up or down, then across; "hv"
  goes across, then up or down.
- "loop" draws an arrow that goes back, out to one side in its own lane.
- "tone" colors an arrow and its label: green for pass, red for fail.
- Arrows are dotted, and the dots move the way the arrow points. "dashed"
  makes a side path: longer dashes that move slower. With "reduce motion" set,
  nothing moves.
- "ticket" sends one dot along the arrows named in "path", in order. It waits
  where an arrow meets a box, and takes each arrow's tone as it goes.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

from itertools import pairwise
from xml.sax.saxutils import escape

from driver import aws
from driver.icons import FOR_KIND, icon

MONO = ("ui-monospace, SFMono-Regular, 'JetBrains Mono', 'Cascadia Mono', Menlo, Consolas, "
        "'Liberation Mono', monospace")

TITLE, SUB, EYEBROW, LABEL = 14, 12, 10.5, 11
ICON, PAD_X, PAD_Y, RADIUS = 18, 14, 12, 4
AWS_ICON = 48
MIN_W, GAP_X, GAP_Y, MARGIN = 180, 48, 40, 24
GROUP_PAD, GROUP_HEAD = 16, 26
KIND_NAMES = {"you": "YOU", "ai": "AI", "server": "SERVER", "check": "CHECK",
              "advisor": "ADVISOR"}

# Arrows are dotted, and the dots move the way the arrow points. A side path
# has longer dashes and moves slower. Readers who ask for less motion get still
# arrows. CSS only: no script, so it runs where SVG shows as an image.
MOTION = (
    ".main{stroke-width:2.6;stroke-dasharray:0 7;animation:flow 0.8s linear infinite}"
    ".side{stroke-width:1.6;stroke-dasharray:6 5;animation:side 1.6s linear infinite}"
    "@keyframes flow{to{stroke-dashoffset:-7}}"
    "@keyframes side{to{stroke-dashoffset:-11}}"
    "@media (prefers-reduced-motion:reduce){.main,.side{animation:none}.ticket{display:none}}"
)

# Every pair passes WCAG 2.1: text 4.5 to 1 on its fill, lines 3 to 1 on the page.
# tests/test_diagrams.py checks this.
THEMES = {
    "light": {
        "page": "#ffffff", "grid": "#eef1f4", "box": "#ffffff", "border": "#d1d9e0",
        "text": "#1f2328", "sub": "#59636e", "edge": "#818b98",
        "kinds": {"you": ("#0969da", "#f3f8ff"), "ai": ("#8250df", "#f9f6ff"),
                  "server": ("#1a7f37", "#f2fbf4"), "check": ("#9a6700", "#fff9e5"),
                  "advisor": ("#bc4c00", "#fff5ee"), "neutral": ("#59636e", "#f6f8fa")},
        "tones": {"fail": "#cf222e", "pass": "#1a7f37"},
    },
    "dark": {
        "page": "#0d1117", "grid": "#161b22", "box": "#151b23", "border": "#3d444d",
        "text": "#f0f6fc", "sub": "#9198a1", "edge": "#656c76",
        "kinds": {"you": ("#4493f8", "#0d1d35"), "ai": ("#ab7df8", "#1b1430"),
                  "server": ("#3fb950", "#0c2114"), "check": ("#d29922", "#221a08"),
                  "advisor": ("#f0883e", "#271608"), "neutral": ("#9198a1", "#151b23")},
        "tones": {"fail": "#f85149", "pass": "#3fb950"},
    },
}


def text_width(s, size, spacing=0.0):
    """Monospace: every character is 0.6 of the font size wide."""
    return len(s) * (size * 0.6 + spacing)


def eyebrow(node):
    if node.get("tag"):
        return node["tag"]
    name = KIND_NAMES.get(node.get("kind"), "")
    if node.get("step") is not None:
        return f"STEP {node['step']}" + (f" · {name}" if name else "")
    return name


def node_size(node):
    title, *sub = node["text"].split("\n")
    if node.get("aws"):
        w = max(text_width(title, TITLE - 1), *(text_width(s, SUB) for s in sub), AWS_ICON) + 16
        return w, AWS_ICON + 12 + 17 * (1 + len(sub))
    head = ICON + 8 + text_width(eyebrow(node), EYEBROW, 1.2)
    w = max(head, text_width(title, TITLE), *(text_width(s, SUB) for s in sub)) + 2 * PAD_X
    h = PAD_Y + ICON + 9 + 16 + 17 * len(sub) + PAD_Y + 2
    return w, h


def label_size(label):
    return text_width(label, LABEL) + 14, 20


def group_depths(spec):
    """How many groups sit inside each group, at most, in a chain."""
    groups = spec.get("groups", [])
    sets = [set(g["nodes"]) for g in groups]
    depth = [0] * len(groups)
    for _ in groups:
        for i, s in enumerate(sets):
            inner = [depth[j] + 1 for j, o in enumerate(sets) if j != i and o < s]
            depth[i] = max(inner, default=0)
    return depth


def layout(spec):
    nodes = spec["nodes"]
    width = max(MIN_W, *(node_size(n)[0] for n in nodes))
    where = {n["id"]: (n["col"], n["row"]) for n in nodes}
    gap_x, gap_y = GAP_X, GAP_Y
    depth = max(group_depths(spec), default=-1)
    if depth >= 0:
        room = GROUP_PAD * (depth + 1)
        gap_x = max(gap_x, 2 * room + 24)
        gap_y = max(gap_y, 2 * room + GROUP_HEAD * (depth + 1) + 16)
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
        top, bottom = ys[n["row"]], ys[n["row"]] + heights[n["row"]]
        boxes[n["id"]] = {"l": left, "t": top, "r": left + width, "b": bottom,
                          "x": left + width / 2, "y": (top + bottom) / 2,
                          "cell": (left, top, left + width, bottom)}
        if n.get("aws"):
            # Arrows meet the icon, not the cell; the name sits under the icon.
            x = left + width / 2
            boxes[n["id"]].update(l=x - AWS_ICON / 2 - 4, r=x + AWS_ICON / 2 + 4, t=top,
                                  b=top + AWS_ICON, y=top + AWS_ICON / 2)
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
            # Start outside any group that holds either end, so the lane clears its border.
            groups = spec.get("groups", [])
            depths = group_depths(spec)
            held = [d for g, d in zip(groups, depths, strict=True)
                    if e["from"] in g["nodes"] or e["to"] in g["nodes"]]
            if held:
                offset += GROUP_PAD * (max(held) + 1) + (GROUP_HEAD if side == "above" else 0)
            lanes[id(e)] = base - offset if side in ("left", "above") else base + offset
            if held:
                offset -= GROUP_PAD * (max(held) + 1) + (GROUP_HEAD if side == "above" else 0)
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


SPEED, WAIT, REST = 240, 0.35, 1.4  # pixels a second; seconds at a box; seconds at the end


def travel(spec, boxes, lanes, t):
    """One dot that follows the ticket's path of arrows, then starts again.

    It runs along each arrow, waits where the arrow meets the next box, and
    jumps to the start of the next arrow. So it never sits on a box's text.
    """
    edges = {(e["from"], e["to"]): e for e in spec["edges"]}
    wait = spec["ticket"].get("wait", {})
    base = t["kinds"]["ai"][0]
    points, marks, colors = [], [], []  # marks: (time, distance along the path)
    now, dist = 0.0, 0.0
    for n, (a, b) in enumerate(spec["ticket"]["path"]):
        e = edges[(a, b)]
        pts, _ = route(e, boxes, lanes)
        if points:
            dist += abs(pts[0][0] - points[-1][0]) + abs(pts[0][1] - points[-1][1])
        points += pts
        marks.append((now, dist))  # the jump to this arrow takes no time
        colors.append((now, t["tones"].get(e.get("tone"), base)))
        if n == 0:
            now += WAIT
            marks.append((now, dist))
        for (x0, y0), (x1, y1) in pairwise(pts):
            step = abs(x1 - x0) + abs(y1 - y0)
            dist += step
            now += step / SPEED
            marks.append((now, dist))
        now += WAIT + wait.get(b, 0)
        marks.append((now, dist))
    now += REST
    marks.append((now, dist))
    dur, total = now, dist
    key_times = ";".join(f"{m[0] / dur:.4f}" for m in marks)
    key_points = ";".join(f"{m[1] / total:.4f}" for m in marks)
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    fill_values = ";".join(c for _, c in colors)
    fill_times = ";".join(f"{c / dur:.4f}" for c, _ in colors)
    shared = f'dur="{dur:.2f}s" repeatCount="indefinite"'
    color = (f'<animate attributeName="fill" values="{fill_values}" keyTimes="{fill_times}" '
             f'calcMode="discrete" {shared}/>')
    return [
        '<g class="ticket">',
        f'<circle r="13" fill="{base}" opacity="0.2">{color}</circle>',
        f'<circle r="6.5" fill="{base}" stroke="{t["page"]}" stroke-width="2">{color}</circle>',
        (f'<animateMotion path="{path}" keyPoints="{key_points}" keyTimes="{key_times}" '
         f'calcMode="linear" {shared}/>'),
        "</g>",
    ]


def draw_groups(spec, boxes, t, seen):
    out = []
    groups = spec.get("groups", [])
    depth = group_depths(spec)
    for i in sorted(range(len(groups)), key=lambda k: -depth[k]):
        g = groups[i]
        inside = [boxes[n]["cell"] for n in g["nodes"]]
        pad = GROUP_PAD * (depth[i] + 1)
        head = GROUP_HEAD * (depth[i] + 1)
        l = min(c[0] for c in inside) - pad
        top = min(c[1] for c in inside) - pad - head + 4
        r = max(c[2] for c in inside) + pad
        bottom = max(c[3] for c in inside) + pad
        seen += [(l, top), (r, bottom)]
        if g.get("aws"):
            svg, color, dashed = aws.group(g["aws"], prefix=f"g{i}")
            dash = ' stroke-dasharray="6 4"' if dashed else ""
            out.append(f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" '
                       f'height="{bottom - top:.1f}" fill="none" stroke="{color}" '
                       f'stroke-width="1.6"{dash}/>')
            out.append(aws.place(svg, l, top, 26))
            out.append(f'<text x="{l + 34:.1f}" y="{top + 17:.1f}" font-size="12" '
                       f'fill="{t["text"]}">{escape(g["label"])}</text>')
            continue
        accent = t["kinds"][g.get("kind", "neutral")][0]
        out.append(f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" '
                   f'height="{bottom - top:.1f}" rx="6" fill="none" stroke="{accent}" '
                   f'stroke-opacity="0.7" stroke-width="1.3" stroke-dasharray="2 4" '
                   f'stroke-linecap="round"/>')
        name = g.get("icon") or FOR_KIND.get(g.get("kind"))
        x = l + 12
        if name:
            out.append(icon(name, x, top + 8, 15, accent, 1.6))
            x += 21
        out.append(f'<text x="{x:.1f}" y="{top + 20:.1f}" font-size="{EYEBROW}" '
                   f'font-weight="700" letter-spacing="1.2" fill="{accent}">'
                   f'{escape(g["label"].upper())}</text>')
    return out


def draw_node(n, bx, t, i):
    out = []
    title, *sub = n["text"].split("\n")
    if n.get("aws"):
        x = bx["x"] - AWS_ICON / 2
        out.append(aws.place(aws.service(n["aws"], prefix=f"n{i}"), x, bx["t"], AWS_ICON))
        y = bx["t"] + AWS_ICON + 18
        out.append(f'<text x="{bx["x"]:.1f}" y="{y:.1f}" text-anchor="middle" '
                   f'font-size="{TITLE - 1}" font-weight="700" fill="{t["text"]}">'
                   f'{escape(title)}</text>')
        for j, s in enumerate(sub):
            out.append(f'<text x="{bx["x"]:.1f}" y="{y + 17 * (j + 1):.1f}" '
                       f'text-anchor="middle" font-size="{SUB}" fill="{t["sub"]}">'
                       f'{escape(s)}</text>')
        return out
    accent, tint = t["kinds"][n.get("kind", "neutral")]
    w, h = bx["r"] - bx["l"], bx["b"] - bx["t"]
    out.append(f'<rect x="{bx["l"]:.1f}" y="{bx["t"]:.1f}" width="{w:.1f}" height="{h:.1f}" '
               f'rx="{RADIUS}" fill="{tint}" stroke="{accent}" stroke-opacity="0.7" '
               f'stroke-width="1.2"/>')
    # Corner ticks, like marks on a drawing.
    for cx, cy, dx, dy in ((bx["l"], bx["t"], 1, 1), (bx["r"], bx["b"], -1, -1)):
        out.append(f'<path d="M{cx + 9 * dx:.1f},{cy - 4 * dy:.1f} H{cx - 4 * dx:.1f} '
                   f'V{cy + 9 * dy:.1f}" fill="none" stroke="{accent}" stroke-width="1.2"/>')
    x, y = bx["l"] + PAD_X, bx["t"] + PAD_Y
    name = n.get("icon") or FOR_KIND.get(n.get("kind"), "ticket")
    out.append(icon(name, x, y, ICON, accent))
    brow = eyebrow(n)
    if brow:
        out.append(f'<text x="{x + ICON + 8:.1f}" y="{y + 13:.1f}" font-size="{EYEBROW}" '
                   f'font-weight="700" letter-spacing="1.2" fill="{accent}">{escape(brow)}</text>')
    y += ICON + 9
    out.append(f'<text x="{x:.1f}" y="{y + 13:.1f}" font-size="{TITLE}" font-weight="700" '
               f'fill="{t["text"]}">{escape(title)}</text>')
    for j, s in enumerate(sub):
        out.append(f'<text x="{x:.1f}" y="{y + 31 + 17 * j:.1f}" font-size="{SUB}" '
                   f'fill="{t["sub"]}">{escape(s)}</text>')
    return out


def draw(spec, theme):
    t = THEMES[theme]
    boxes = layout(spec)
    lanes = loop_lanes(spec, boxes)
    seen = []
    for bx in boxes.values():
        seen += [bx["cell"][:2], bx["cell"][2:]]
    groups = draw_groups(spec, boxes, t, seen)

    edges, labels = [], []
    for e in spec.get("edges", []):
        pts, mid = route(e, boxes, lanes)
        seen += pts
        tone = e.get("tone")
        color = t["tones"].get(tone, t["edge"])
        flow = "side" if e.get("dashed") else "main"
        edges.append(f'<path class="{flow}" d="{rounded(pts)}" fill="none" stroke="{color}" '
                     f'stroke-linecap="round" stroke-linejoin="round" '
                     f'marker-end="url(#arrow-{tone or "plain"})"/>')
        if e.get("label"):
            w, h = label_size(e["label"])
            ink = t["tones"].get(tone, t["sub"])
            frame = t["tones"].get(tone, t["border"])
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
            labels.append(f'<rect x="{mid[0] - w / 2:.1f}" y="{mid[1] - h / 2:.1f}" '
                          f'width="{w:.1f}" height="{h}" rx="3" fill="{t["page"]}" '
                          f'stroke="{frame}" stroke-width="1"/>')
            labels.append(f'<text x="{mid[0]:.1f}" y="{mid[1] + 3.8:.1f}" text-anchor="middle" '
                          f'font-size="{LABEL}" fill="{ink}">{escape(e["label"])}</text>')

    body = []
    for i, n in enumerate(spec["nodes"]):
        body += draw_node(n, boxes[n["id"]], t, i)
    ticket = travel(spec, boxes, lanes, t) if spec.get("ticket") else []

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
    grid = (f'<pattern id="grid" x="{x0:.0f}" y="{y0:.0f}" width="24" height="24" '
            f'patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" '
            f'stroke="{t["grid"]}" stroke-width="1"/></pattern>')
    head = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" '
         f'width="{w:.0f}" height="{h:.0f}" role="img" aria-labelledby="title desc" '
         f'font-family="{MONO}">'),
        f'<title id="title">{escape(spec["title"])}</title>',
        f'<desc id="desc">{escape(spec["desc"])}</desc>',
        f'<defs>{"".join(markers)}{grid}</defs>',
        f"<style>{MOTION}</style>",
        # A full square: no corner is see-through, whatever the page behind it.
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{t["page"]}"/>',
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="url(#grid)"/>',
    ]
    return "\n".join(head + groups + edges + body + labels + ticket + ["</svg>"]) + "\n"
