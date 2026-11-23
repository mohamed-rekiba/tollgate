"""Draw a diagram as SVG, in a light and a dark theme: the flat blueprint style.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "nodes": [{"id": "a", "text": "Title\\nOne line under it", "col": 0, "row": 0,
                "shape": "step" | "start" | "end" | "decision" | "io" | "document" |
                         "data" | "subprocess" | "wait" | "manual" | "person" | "queue" |
                         "node" | "oval",
                "kind": "you" | "ai" | "server" | "check" | "advisor",
                "icon": "lock", "tag": "OWN LABEL", "step": 1,
                "aws": "s3"}],
     "edges": [{"from": "a", "to": "b", "label": "optional",
                "tone": "pass" | "fail", "dashed": true,
                "loop": "left" | "right" | "above" | "below",
                "route": "vhv" | "vh" | "hv", "arrow": false}],
     "names": {"server": "GitHub"},
     "heading": "A title drawn over the diagram",
     "groups": [{"label": "The server", "nodes": ["a", "b"], "kind": "server",
                 "icon": "lock", "aws": "vpc",
                 "style": "boundary" | "node" | "system", "type": "Software System"}],
     "ticket": {"path": [["a", "b"], ["b", "c"]], "wait": {"b": 1.2}}}

The design:
- A fine grid behind everything, monospace type, square tags.
- "shape" follows the flowchart standard (ISO 5807): "start" and "end" are
  pills, a "step" is a box, a "decision" is a diamond, "io" (something comes in
  or goes out) is a slanted box, a "document" has a wavy foot, "data" (stored,
  like a database or locked tests) is a cylinder, a "subprocess" (a step
  described elsewhere) has double sides, "wait" is a D, and "manual" (a person
  does it by hand) is a trapezoid.
- Four more shapes serve architecture and UML: "person" (a head over a box
  with round shoulders), "queue" (a pipe on its side), "node" (a box in three
  dimensions, a machine or a place that runs software), and "oval" (a UML use
  case).
- Nodes sit on a grid of columns and rows. All boxes share one width.
- "kind" says who acts. It sets the color, the icon, and the small label over
  the title (YOU, AI, SERVER, CHECK, ADVISOR). "names" renames those labels
  for the whole diagram, such as {"server": "GitHub"}. "icon" picks another icon from
  diagram/icons.py. "step" adds STEP n. "tag" replaces the label. A box with
  no kind is neutral slate.
- "aws" draws the official AWS service icon with its name under it, the way
  AWS diagrams do. The icons come from a local copy of the AWS package; see
  diagram/aws.py.
- "groups" draw a border around nodes: a place, a boundary, or an AWS group
  ("aws": "cloud", "region", "az", "vpc", "public subnet", "private subnet",
  "security group", ...), in AWS's own color with its group icon. Groups may
  nest; inner ones must hold a subset of the outer one's nodes, or the same
  nodes when the inner one is listed later.
- A group's "style" draws it as a border of architecture: "boundary" is a
  dashed box with the label in bold and "type" after it in brackets, as in
  "Tollgate [Software System]"; "node" is a box in three dimensions with
  "type" after the label as a UML stereotype, as in "Your machine «device»";
  "system" is a plain box with the label in bold, a UML system's border.
- Arrows are straight, or bend at right angles with round corners. "route"
  picks the bends for an arrow between two rows and two columns: "vhv" (the
  default) goes down, across, down; "vh" goes up or down, then across; "hv"
  goes across, then up or down.
- "loop" draws an arrow that goes back, out to one side in its own lane.
- "tone" colors an arrow and its label: green for pass, red for fail.
- A label may have two lines, split by "\n".
- "arrow": false draws a plain line with no head that does not move: a link
  with no direction, such as a UML association.
- Arrows are dotted, and the dots move the way the arrow points. "dashed"
  makes a side path: longer dashes that move slower. With "reduce motion" set,
  nothing moves.
- "ticket" sends one dot along the arrows named in "path", in order. It waits
  where an arrow meets a box, and takes each arrow's tone as it goes.
- "heading" draws a title in bold over the top left of the diagram.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

from itertools import pairwise
from xml.sax.saxutils import escape

from diagram import aws
from diagram.icons import FOR_KIND, icon

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
    name = node.get("kind_name") or KIND_NAMES.get(node.get("kind"), "")
    if node.get("step") is not None:
        return f"STEP {node['step']}" + (f" · {name}" if name else "")
    return name


# Flowchart shapes (ISO 5807): what each step is decides its outline.
SHAPES = ("step", "start", "end", "decision", "io", "document", "data", "subprocess", "wait",
          "manual", "person", "queue", "node", "oval")
GROUP_STYLES = ("boundary", "node", "system")
HEAD_R, SHOULDER, DEPTH = 15, 26, 10   # a person's head and where its body starts; a node's depth
# Room each shape needs around its text: left, right, top, bottom.
INSETS = {"step": (0, 0, 0, 0), "start": (14, 14, 0, 0), "end": (14, 14, 0, 0),
          "io": (16, 16, 0, 0), "document": (0, 0, 0, 10), "data": (0, 0, 12, 4),
          "subprocess": (10, 10, 0, 0), "wait": (0, 18, 0, 0), "manual": (16, 16, 0, 0),
          "decision": (0, 0, 0, 0), "person": (0, 0, SHOULDER, 0), "queue": (8, 22, 0, 0),
          "node": (0, DEPTH, DEPTH, 0), "oval": (24, 24, 8, 8)}
CENTERED = {"start", "end", "decision", "oval"}


def content_size(node):
    title, *sub = node["text"].split("\n")
    head = ICON + 8 + text_width(eyebrow(node), EYEBROW, 1.2)
    w = max(head, text_width(title, TITLE), *(text_width(s, SUB) for s in sub))
    h = ICON + 9 + 16 + 17 * len(sub)
    return w, h


def node_size(node):
    title, *sub = node["text"].split("\n")
    if node.get("aws"):
        w = max(text_width(title, TITLE - 1), *(text_width(s, SUB) for s in sub), AWS_ICON) + 16
        return w, AWS_ICON + 12 + 17 * (1 + len(sub))
    w, h = content_size(node)
    shape = node.get("shape", "step")
    if shape == "decision":
        return w * 1.75 + 28, h * 1.8 + 16
    left, right, top, bottom = INSETS[shape]
    return w + 2 * PAD_X + left + right, h + 2 * PAD_Y + 2 + top + bottom


def label_size(label):
    lines = label.split("\n")
    return max(text_width(s, LABEL) for s in lines) + 14, 20 + 14 * (len(lines) - 1)


def group_label_width(g):
    """How wide a group's label runs, from its left border."""
    if g.get("style") in GROUP_STYLES:
        extra = text_width(f"[{g['type']}]", SUB - 1) + 8 if g.get("type") else 0
        return 12 + text_width(g["label"], TITLE - 1) + extra + 12
    return 12 + 21 + text_width(g["label"], EYEBROW, 1.2) + 12


def group_depths(spec):
    """How many groups sit inside each group, at most, in a chain."""
    groups = spec.get("groups", [])
    sets = [set(g["nodes"]) for g in groups]
    depth = [0] * len(groups)
    for _ in groups:
        for i, s in enumerate(sets):
            # The same nodes: the group listed later is the inner one.
            inner = [depth[j] + 1 for j, o in enumerate(sets) if o < s or (o == s and j > i)]
            depth[i] = max(inner, default=0)
    return depth


def group_spans(spec):
    """For each group: its depth and the columns and rows its nodes cover."""
    where = {n["id"]: (n["col"], n["row"]) for n in spec["nodes"]}
    out = []
    for g, d in zip(spec.get("groups", []), group_depths(spec), strict=True):
        cols = [where[n][0] for n in g["nodes"]]
        rows = [where[n][1] for n in g["nodes"]]
        out.append((d, min(cols), max(cols), min(rows), max(rows)))
    return out


def gaps(order, spans, base, before, after, labels):
    """The gap after each column (or row) in `order`: room for the group borders
    that end there and start next, and for labels on arrows that cross it."""
    out = {}
    for a, b in pairwise(order):
        end = max((after(d) for d, lo, hi in spans if hi == a), default=0)
        begin = max((before(d) for d, lo, hi in spans if lo == b), default=0)
        need = end + begin + 16 if end or begin else 0
        # A label sits in the middle of the gap, clear of the borders on both sides.
        label = labels.get(a, 0) + 2 * max(end, begin) if a in labels else 0
        out[a] = max(base, need, label)
    return out


def layout(spec):
    nodes = spec["nodes"]
    boxes_w = [node_size(n)[0] for n in nodes if n.get("shape") != "decision"]
    width = max(MIN_W, *boxes_w) if boxes_w else MIN_W
    # A group in one column is as wide as its label.
    for g, (d, lo, hi, _, _) in zip(spec.get("groups", []), group_spans(spec), strict=True):
        if lo == hi:
            width = max(width, group_label_width(g) - 2 * GROUP_PAD * (d + 1))
    column = max(width, *(node_size(n)[0] for n in nodes))
    where = {n["id"]: (n["col"], n["row"]) for n in nodes}
    # Labels on straight arrows need room in the gap they cross.
    col_labels, row_labels = {}, {}
    for e in spec.get("edges", []):
        if not e.get("label") or e.get("loop"):
            continue
        (c1, r1), (c2, r2) = where[e["from"]], where[e["to"]]
        lw, lh = label_size(e["label"])
        if r1 == r2:
            col_labels[min(c1, c2)] = max(col_labels.get(min(c1, c2), 0), lw + 28)
        elif c1 == c2:
            row_labels[min(r1, r2)] = max(row_labels.get(min(r1, r2), 0), lh + 44)
    spans = group_spans(spec)
    cols = sorted({n["col"] for n in nodes})
    rows = sorted({n["row"] for n in nodes})
    # Each gap gets only the room its own borders need: an inner border, then
    # each border around it, each with its label above.
    col_gap = gaps(cols, [(d, lo, hi) for d, lo, hi, _, _ in spans], GAP_X,
                   lambda d: GROUP_PAD * (d + 1), lambda d: GROUP_PAD * (d + 1), col_labels)
    row_gap = gaps(rows, [(d, lo, hi) for d, _, _, lo, hi in spans], GAP_Y,
                   lambda d: (GROUP_PAD + GROUP_HEAD) * (d + 1), lambda d: GROUP_PAD * (d + 1),
                   row_labels)
    xs, x = {}, 0
    for c in cols:
        xs[c] = x
        x += column + col_gap.get(c, 0)
    # A row is as tall as its boxes. A diamond keeps its own height and reaches
    # into the gaps above and below its row.
    heights, tall = {}, {}
    for n in nodes:
        h = node_size(n)[1]
        if n.get("shape") == "decision":
            tall[n["row"]] = max(tall.get(n["row"], 0), h)
        else:
            heights[n["row"]] = max(heights.get(n["row"], 0), h)
    for r, h in tall.items():
        heights.setdefault(r, min(h, 80))
    over = {r: max(0, (tall.get(r, 0) - heights[r]) / 2) for r in heights}
    ys, y = {}, 0
    for i, r in enumerate(rows):
        y += over[r] if i == 0 else 0
        ys[r] = y
        nxt = over[rows[i + 1]] if i + 1 < len(rows) else 0
        y += heights[r] + over[r] + row_gap.get(r, 0) + nxt
    aws_rows = {n["row"] for n in nodes if n.get("aws")}
    boxes = {}
    for n in nodes:
        own = node_size(n)[0] if n.get("shape") == "decision" else width
        left = xs[n["col"]] + (column - own) / 2
        top, bottom = ys[n["row"]], ys[n["row"]] + heights[n["row"]]
        if n.get("shape") == "decision":
            mid, half = (top + bottom) / 2, node_size(n)[1] / 2
            top, bottom = mid - half, mid + half
        bx = {"l": left, "t": top, "r": left + own, "b": bottom, "x": left + own / 2,
              "y": (top + bottom) / 2, "row": n["row"], "col": n["col"],
              "cell": (left, top, left + own, bottom)}
        if n.get("aws"):
            # Arrows meet the icon at its sides and top, and leave from below its
            # name, so no arrow crosses the words under an icon.
            cx = left + own / 2
            bx.update(l=cx - AWS_ICON / 2 - 4, r=cx + AWS_ICON / 2 + 4, y=top + AWS_ICON / 2,
                      b=top + node_size(n)[1])
        elif n["row"] in aws_rows and n.get("shape") != "decision":
            # In a row with AWS icons, arrows run level with the icons.
            bx["y"] = top + AWS_ICON / 2
        boxes[n["id"]] = bx
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


def travel(spec, boxes, lanes, t, arrow=None):
    """One dot that follows the ticket's path of arrows, then starts again.

    It runs along each arrow, waits where the arrow meets the next box, and
    jumps to the start of the next arrow. So it never sits on a box's text.
    `arrow(a, b)` gives the points and the tone of the arrow from a to b; by
    default, the flow's own edge.
    """
    if arrow is None:
        edges = {(e["from"], e["to"]): e for e in spec["edges"]}

        def arrow(a, b):
            e = edges[(a, b)]
            return route(e, boxes, lanes)[0], e.get("tone")

    wait = spec["ticket"].get("wait", {})
    base = t["kinds"]["ai"][0]
    points, marks, colors = [], [], []  # marks: (time, distance along the path)
    now, dist = 0.0, 0.0
    for n, (a, b) in enumerate(spec["ticket"]["path"]):
        pts, tone = arrow(a, b)
        if points:
            dist += abs(pts[0][0] - points[-1][0]) + abs(pts[0][1] - points[-1][1])
        points += pts
        marks.append((now, dist))  # the jump to this arrow takes no time
        colors.append((now, t["tones"].get(tone, base)))
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


def draw_groups(spec, boxes, t, seen, front):
    """The borders of the groups. The label of a styled group goes in `front`,
    over the arrows, on a patch of the page, so an arrow that crosses it hides."""
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
        if g.get("style") in GROUP_STYLES:
            out += styled_group(g, (l, top, r, bottom), t, seen, front)
            continue
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


def styled_group(g, edges, t, seen, front):
    """A border of architecture: a C4 boundary, a UML node, or a UML system."""
    l, top, r, bottom = edges
    style = g["style"]
    accent, tint = t["kinds"][g.get("kind", "neutral")]
    dash = ' stroke-dasharray="7 5"' if style == "boundary" else ""
    rx = {"boundary": 6, "system": 4, "node": 0}[style]
    out = [f'<g class="{style}">',
           (f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" height="{bottom - top:.1f}" '
            f'rx="{rx}" fill="none" stroke="{accent}" stroke-width="1.4"{dash}/>')]
    if style == "node":
        d = DEPTH * 0.8
        seen.append((r + d, top - d))
        out += faces(l, top, r, bottom, d, accent, tint)
    x, y = l + 12, top + 18
    words = [(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{TITLE - 1}" font-weight="700" '
              f'fill="{t["text"]}">{escape(g["label"])}</text>')]
    if g.get("type"):
        kind = f"«{g['type']}»" if style == "node" else f"[{g['type']}]"
        x += text_width(g["label"], TITLE - 1) + 8
        words.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{SUB - 1}" fill="{t["sub"]}">'
                     f'{escape(kind)}</text>')
    end = l + group_label_width(g) - 6
    front += [f'<g class="{style}-label">',
              (f'<rect x="{l + 6:.1f}" y="{top + 4:.1f}" width="{end - l - 12:.1f}" height="19" '
               f'fill="{t["page"]}"/>'), *words, "</g>"]
    return [*out, "</g>"]


def faces(l, top, r, b, d, accent, tint):
    """The top face and the right face of a box in three dimensions, behind its front."""
    paint = f'fill="{tint}" stroke="{accent}" stroke-width="1.3" stroke-linejoin="round"'
    return [(f'<polygon points="{l:.1f},{top:.1f} {l + d:.1f},{top - d:.1f} '
             f'{r + d:.1f},{top - d:.1f} {r:.1f},{top:.1f}" {paint}/>'),
            (f'<polygon points="{r:.1f},{top:.1f} {r + d:.1f},{top - d:.1f} '
             f'{r + d:.1f},{b - d:.1f} {r:.1f},{b:.1f}" {paint}/>')]


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
    shape = n.get("shape", "step")
    out.append(f'<g class="{shape}">')
    out.append(outline(shape, bx, accent, tint))
    if shape == "step":
        # Corner ticks, like marks on a drawing.
        for cx, cy, dx, dy in ((bx["l"], bx["t"], 1, 1), (bx["r"], bx["b"], -1, -1)):
            out.append(f'<path d="M{cx + 9 * dx:.1f},{cy - 4 * dy:.1f} H{cx - 4 * dx:.1f} '
                       f'V{cy + 9 * dy:.1f}" fill="none" stroke="{accent}" stroke-width="1.2"/>')
    out += content(n, bx, t, accent, shape)
    return [*out, "</g>"]


def outline(shape, bx, accent, tint):
    """The outline of one node, by its flowchart shape."""
    l, r, top, b = bx["l"], bx["r"], bx["t"], bx["b"]
    w, h = r - l, b - top
    paint = f'fill="{tint}" stroke="{accent}" stroke-width="1.3" stroke-linejoin="round"'
    if shape in ("start", "end"):
        return f'<rect x="{l:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h / 2:.1f}" {paint}/>'
    if shape == "decision":
        return (f'<polygon points="{bx["x"]:.1f},{top:.1f} {r:.1f},{bx["y"]:.1f} '
                f'{bx["x"]:.1f},{b:.1f} {l:.1f},{bx["y"]:.1f}" {paint}/>')
    if shape == "io":
        k = 14
        return f'<polygon points="{l + k:.1f},{top:.1f} {r:.1f},{top:.1f} {r - k:.1f},{b:.1f} {l:.1f},{b:.1f}" {paint}/>'
    if shape == "manual":
        k = 14
        return f'<polygon points="{l:.1f},{top:.1f} {r:.1f},{top:.1f} {r - k:.1f},{b:.1f} {l + k:.1f},{b:.1f}" {paint}/>'
    if shape == "document":
        wave = 8
        return (f'<path d="M{l:.1f},{top:.1f} H{r:.1f} V{b - wave:.1f} '
                f'C{r - w * 0.25:.1f},{b - 2 * wave:.1f} {l + w * 0.6:.1f},{b + wave:.1f} '
                f'{l:.1f},{b - wave / 2:.1f} Z" {paint}/>')
    if shape == "data":
        ry = 8
        return (f'<path d="M{l:.1f},{top + ry:.1f} A{w / 2:.1f},{ry} 0 0 1 {r:.1f},{top + ry:.1f} '
                f'V{b - ry:.1f} A{w / 2:.1f},{ry} 0 0 1 {l:.1f},{b - ry:.1f} Z" {paint}/>'
                f'<path d="M{l:.1f},{top + ry:.1f} A{w / 2:.1f},{ry} 0 0 0 {r:.1f},{top + ry:.1f}" '
                f'fill="none" stroke="{accent}" stroke-width="1.3"/>')
    if shape == "wait":
        k = h / 2
        return (f'<path d="M{l:.1f},{top:.1f} H{r - k:.1f} A{k:.1f},{k:.1f} 0 0 1 {r - k:.1f},{b:.1f} '
                f'H{l:.1f} Z" {paint}/>')
    if shape == "person":
        body = top + SHOULDER
        return (f'<rect x="{l:.1f}" y="{body:.1f}" width="{w:.1f}" height="{b - body:.1f}" '
                f'rx="20" {paint}/><circle cx="{bx["x"]:.1f}" cy="{top + HEAD_R:.1f}" '
                f'r="{HEAD_R}" {paint}/>')
    if shape == "queue":
        k = 10
        return (f'<path d="M{l + k:.1f},{top:.1f} H{r - k:.1f} A{k},{h / 2:.1f} 0 0 1 {r - k:.1f},{b:.1f} '
                f'H{l + k:.1f} A{k},{h / 2:.1f} 0 0 1 {l + k:.1f},{top:.1f} Z" {paint}/>'
                f'<path d="M{r - k:.1f},{top:.1f} A{k},{h / 2:.1f} 0 0 0 {r - k:.1f},{b:.1f}" '
                f'fill="none" stroke="{accent}" stroke-width="1.3"/>')
    if shape == "node":
        d = DEPTH
        return (f'<rect x="{l:.1f}" y="{top + d:.1f}" width="{w - d:.1f}" height="{h - d:.1f}" '
                f'{paint}/>' + "".join(faces(l, top + d, r - d, b, d, accent, tint)))
    if shape == "oval":
        return (f'<ellipse cx="{bx["x"]:.1f}" cy="{bx["y"]:.1f}" rx="{w / 2:.1f}" ry="{h / 2:.1f}" '
                f'{paint}/>')
    if shape == "subprocess":
        return (f'<rect x="{l:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" {paint}/>'
                f'<path d="M{l + 8:.1f},{top:.1f} V{b:.1f} M{r - 8:.1f},{top:.1f} V{b:.1f}" '
                f'stroke="{accent}" stroke-width="1.3"/>')
    return f'<rect x="{l:.1f}" y="{top:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{RADIUS}" {paint}/>'


def content(n, bx, t, accent, shape):
    """The icon, the label over the title, the title, and the lines under it."""
    out = []
    title, *sub = n["text"].split("\n")
    _, ch = content_size(n)
    name = n.get("icon") or FOR_KIND.get(n.get("kind"), "ticket")
    brow = eyebrow(n)
    if shape in CENTERED:
        y = bx["y"] - ch / 2
        head_w = ICON + (8 + text_width(brow, EYEBROW, 1.2) if brow else 0)
        hx = bx["x"] - head_w / 2
        out.append(icon(name, hx, y, ICON, accent))
        if brow:
            out.append(f'<text x="{hx + ICON + 8:.1f}" y="{y + 13:.1f}" font-size="{EYEBROW}" '
                       f'font-weight="700" letter-spacing="1.2" fill="{accent}">{escape(brow)}</text>')
        y += ICON + 9
        out.append(f'<text x="{bx["x"]:.1f}" y="{y + 13:.1f}" text-anchor="middle" '
                   f'font-size="{TITLE}" font-weight="700" fill="{t["text"]}">{escape(title)}</text>')
        for j, s in enumerate(sub):
            out.append(f'<text x="{bx["x"]:.1f}" y="{y + 31 + 17 * j:.1f}" text-anchor="middle" '
                       f'font-size="{SUB}" fill="{t["sub"]}">{escape(s)}</text>')
        return out
    left, _, top, _ = INSETS[shape]
    x, y = bx["l"] + PAD_X + left, bx["t"] + PAD_Y + top
    out.append(icon(name, x, y, ICON, accent))
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


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    from diagram.aws import GROUPS
    from diagram.icons import ICONS
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    if not spec.get("nodes"):
        raise ValueError("the diagram has no nodes")
    ids = [n["id"] for n in spec["nodes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("two nodes share an id")
    ids = set(ids)
    kinds = set(THEMES["light"]["kinds"])
    for n in spec["nodes"]:
        if n.get("kind", "neutral") not in kinds:
            raise ValueError(f"node '{n['id']}': kind must be one of {', '.join(sorted(kinds))}")
        if n.get("shape", "step") not in SHAPES:
            raise ValueError(f"node '{n['id']}': shape must be one of {', '.join(SHAPES)}")
        if n.get("icon") and n["icon"] not in ICONS:
            raise ValueError(f"node '{n['id']}': no icon named '{n['icon']}'")
    for e in spec.get("edges", []):
        for end in ("from", "to"):
            if e[end] not in ids:
                raise ValueError(f"an arrow {end} '{e[end]}', which is not a node")
        if e.get("tone") not in (None, "pass", "fail"):
            raise ValueError("an arrow's tone must be 'pass' or 'fail'")
    for g in spec.get("groups", []):
        if g.get("aws") and g["aws"] not in GROUPS:
            raise ValueError(f"no AWS group '{g['aws']}'; use one of {', '.join(GROUPS)}")
        if g.get("style") not in (None, *GROUP_STYLES):
            raise ValueError(f"group '{g.get('label')}': style must be one of "
                             f"{', '.join(GROUP_STYLES)}")
        if not g.get("nodes") or set(g["nodes"]) - ids:
            raise ValueError(f"group '{g.get('label')}' names nodes that do not exist")
    for a, b in (spec.get("ticket") or {}).get("path", []):
        if not any(e["from"] == a and e["to"] == b for e in spec.get("edges", [])):
            raise ValueError(f"the ticket's path uses an arrow {a} -> {b} that is not drawn")
    if spec.get("ticket") is not None and not spec["ticket"].get("path"):
        raise ValueError("the ticket has an empty path")


def draw(spec, theme):
    check(spec)
    names = {k: v.upper() for k, v in (spec.get("names") or {}).items()}
    if names:
        spec = dict(spec, nodes=[dict(n, kind_name=names[n["kind"]]) if n.get("kind") in names
                                 else n for n in spec["nodes"]])
    t = THEMES[theme]
    boxes = layout(spec)
    lanes = loop_lanes(spec, boxes)
    seen = []
    for bx in boxes.values():
        seen += [bx["cell"][:2], bx["cell"][2:]]
    front = []
    groups = draw_groups(spec, boxes, t, seen, front)

    edges, labels = [], []
    for e in spec.get("edges", []):
        pts, mid = route(e, boxes, lanes)
        seen += pts
        tone = e.get("tone")
        color = t["tones"].get(tone, t["edge"])
        if e.get("arrow", True):
            flow = "side" if e.get("dashed") else "main"
            edges.append(f'<path class="{flow}" d="{rounded(pts)}" fill="none" stroke="{color}" '
                         f'stroke-linecap="round" stroke-linejoin="round" '
                         f'marker-end="url(#arrow-{tone or "plain"})"/>')
        else:
            edges.append(f'<path class="line" d="{rounded(pts)}" fill="none" stroke="{color}" '
                         f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
        if e.get("label"):
            w, h = label_size(e["label"])
            ink = t["tones"].get(tone, t["sub"])
            frame = t["tones"].get(tone, t["border"])
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
            labels.append(f'<rect class="label" x="{mid[0] - w / 2:.1f}" y="{mid[1] - h / 2:.1f}" '
                          f'width="{w:.1f}" height="{h}" rx="3" fill="{t["page"]}" '
                          f'stroke="{frame}" stroke-width="1"/>')
            for j, line in enumerate(e["label"].split("\n")):
                y = mid[1] - h / 2 + 13.8 + 14 * j
                labels.append(f'<text x="{mid[0]:.1f}" y="{y:.1f}" text-anchor="middle" '
                              f'font-size="{LABEL}" fill="{ink}">{escape(line)}</text>')

    body = []
    for i, n in enumerate(spec["nodes"]):
        body += draw_node(n, boxes[n["id"]], t, i)
    ticket = travel(spec, boxes, lanes, t) if spec.get("ticket") else []
    if spec.get("heading"):
        hx, hy = min(p[0] for p in seen), min(p[1] for p in seen) - 16
        seen += [(hx, hy - 14), (hx + text_width(spec["heading"], 16), hy)]
        labels.append(f'<text x="{hx:.1f}" y="{hy:.1f}" font-size="16" font-weight="700" '
                      f'fill="{t["text"]}">{escape(spec["heading"])}</text>')

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
    return "\n".join(head + groups + edges + front + body + labels + ticket + ["</svg>"]) + "\n"
