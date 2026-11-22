"""Draw a UML state machine as SVG, in a light and a dark theme: the flat blueprint style.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"type": "state",
     "title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "names": {"server": "Your machine"},
     "states": [{"id": "start", "initial": true, "col": 0, "row": 0},
                {"id": "a", "text": "Title\\nOne line under it", "col": 1, "row": 0,
                 "kind": "you" | "ai" | "server" | "check" | "advisor",
                 "icon": "plan", "parent": "p"},
                {"id": "p", "text": "Title\\nOne line under it", "col": 2, "row": 0,
                 "kind": "ai"},
                {"id": "done", "final": true, "col": 3, "row": 0}],
     "transitions": [{"from": "start", "to": "a"},
                     {"from": "a", "to": "b", "event": "plan approved",
                      "guard": "no question is open", "tone": "pass" | "fail",
                      "loop": "left" | "right" | "above" | "below",
                      "route": "vhv" | "vh" | "hv", "shift": 12}],
     "ticket": {"path": [["start", "a"], ["a", "b"]], "wait": {"b": 1.2}}}

The design follows UML, drawn in Tollgate's style:
- A fine grid behind everything, monospace type, the same colors as a flow.
- A state is a box with round corners. It has an icon, a small label over the
  title, the title, and at most two short lines under it. "kind" says who acts
  in that state. It sets the color, the icon, and the small label (YOU, AI,
  SERVER, CHECK, ADVISOR). "names" renames those labels for the whole diagram,
  such as {"server": "Your machine"}. "icon" picks another icon from
  diagram/icons.py. A state with no kind is neutral slate.
- "initial": true is where the machine starts: a small filled dot. There is
  at most one in the top level and one in each state with children.
  "final": true is where it ends: a ring with a dot inside. Neither has a text.
- States sit on a grid of columns and rows. All states share one width. Each
  column is as wide as its widest state, and each row as tall as its tallest.
- "parent" puts a state inside another one, one level deep. The outer state is
  a larger box with its title in a band at the top, and its children sit inside
  on their own grid of "col" and "row". The outer state starts at the left edge
  of its own column and reaches right as far as it needs: keep the cells it
  covers empty. A transition may start or end at the outer box or at a child.
- A transition is an arrow with a label: the event, then the guard in square
  brackets, as in "plan approved [no question is open]". Both are optional.
  "tone" colors the arrow and its label: green for pass, red for fail.
- An arrow between two states that face each other is straight. Otherwise it
  bends at right angles with round corners: "route" picks the bends. "vhv" (the
  default) goes down, across, down; "vh" goes up or down, then across; "hv"
  goes across, then up or down.
- "loop" sends an arrow out to one side in its own lane, for an arrow that goes
  back. When "from" and "to" are the same state, it is a self-transition: a
  small loop on that side of the state ("above" by default).
- "shift" moves the ends of an arrow along the sides of the boxes, in pixels,
  so two arrows can share a side. One number moves the whole arrow; a pair
  [from, to] moves the first leg and the last leg on their own. Two straight
  arrows that go both ways between two states take a shift each, such as -12
  and 12, and their labels then sit beside them.
- Transitions are solid lines, as in UML. Only the ticket's dot moves, and
  with "reduce motion" set, it is hidden.
- "ticket" sends one dot along the transitions named in "path", in order. It
  waits where an arrow meets a state, and takes each arrow's tone as it goes.
  "wait" adds seconds at a state.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

from xml.sax.saxutils import escape

from diagram import flow
from diagram.flow import (
    EYEBROW,
    ICON,
    KIND_NAMES,
    LABEL,
    MARGIN,
    MIN_W,
    MONO,
    MOTION,
    PAD_X,
    PAD_Y,
    SUB,
    THEMES,
    TITLE,
    rounded,
    text_width,
)
from diagram.icons import FOR_KIND, ICONS, icon

RADIUS, PARENT_RADIUS = 12, 16   # rounder than a flow step: the UML state look
GAP_X, GAP_Y = 56, 48
PAD = 20                         # room inside a state with children, around them
DOT, RING = 7, 11                # the initial dot and the final ring
LOOP, LOOP_HALF = 26, 14         # how far a self-transition reaches out, and half its width
SIDES = ("left", "right", "above", "below")
ROUTES = ("vhv", "vh", "hv")


def pseudo(s):
    return "initial" if s.get("initial") else "final" if s.get("final") else None


def label_of(tr):
    guard = f"[{tr['guard']}]" if tr.get("guard") else ""
    return " ".join(p for p in (tr.get("event", ""), guard) if p)


def label_size(text):
    return text_width(text, LABEL) + 14, 20


def shifts(tr):
    s = tr.get("shift", 0)
    return (s[0], s[1]) if isinstance(s, list) else (s, s)


def eyebrow(s, names):
    kind = s.get("kind")
    return names.get(kind) or KIND_NAMES.get(kind, "")


def content_size(s, names):
    title, *sub = s["text"].split("\n")
    brow = eyebrow(s, names)
    head = ICON + (8 + text_width(brow, EYEBROW, 1.2) if brow else 0)
    w = max(head, text_width(title, TITLE), *(text_width(x, SUB) for x in sub))
    return w, ICON + 9 + 16 + 17 * len(sub)


def box(l, t, w, h):
    return {"l": l, "t": t, "r": l + w, "b": t + h, "x": l + w / 2, "y": t + h / 2}


def moved(b, dx, dy):
    return box(b["l"] + dx, b["t"] + dy, b["r"] - b["l"], b["b"] - b["t"])


# Layout.

def grid(members, sizes, trs, parents):
    """Place the states of one level on their grid, in their own units."""
    ids = {s["id"] for s in members}
    where = {s["id"]: (s["col"], s["row"]) for s in members}
    cols = sorted({c for c, _ in where.values()})
    rows = sorted({r for _, r in where.values()})
    colw = {}
    for c in cols:
        plain = [sizes[s["id"]][0] for s in members if s["col"] == c and s["id"] not in parents]
        colw[c] = max(plain or [sizes[s["id"]][0] for s in members if s["col"] == c])
    leaf_h = {}
    for s in members:
        if not pseudo(s) and s["id"] not in parents:
            leaf_h[s["row"]] = max(leaf_h.get(s["row"], 0), sizes[s["id"]][1])
    rowh = {r: max(sizes[s["id"]][1] for s in members if s["row"] == r) for r in rows}
    # The gaps grow for the labels and the self-transitions that sit in them.
    col_need, row_need = {}, {}

    def need(d, k, v):
        if k is not None:
            d[k] = max(d.get(k, 0), v)

    def before(order, k):
        i = order.index(k)
        return order[i - 1] if i else None

    for tr in trs:
        a, b = tr["from"], tr["to"]
        if a not in ids or b not in ids:
            continue
        text = label_of(tr)
        lw, lh = label_size(text) if text else (0, 0)
        (c1, r1), (c2, r2) = where[a], where[b]
        if a == b:
            side = tr.get("loop", "above")
            tall, wide = LOOP + lh + 24, LOOP + lw + 20
            if side == "above":
                need(row_need, before(rows, r1), tall)
            elif side == "below":
                need(row_need, r1, tall)
            elif side == "left":
                need(col_need, before(cols, c1), wide)
            else:
                need(col_need, c1, wide)
        elif text and not tr.get("loop"):
            if r1 == r2:
                need(col_need, min(c1, c2), lw + 28)
            else:
                need(row_need, min(r1, r2), lh + 44)
    xs, x = {}, 0
    for c in cols:
        xs[c] = x
        x += colw[c] + max(GAP_X, col_need.get(c, 0))
    ys, y = {}, 0
    for r in rows:
        ys[r] = y
        y += rowh[r] + max(GAP_Y, row_need.get(r, 0))
    boxes = {}
    for s in members:
        c, r = s["col"], s["row"]
        w, h = sizes[s["id"]]
        if not pseudo(s) and s["id"] not in parents:
            h = leaf_h[r]
        left = xs[c] if s["id"] in parents else xs[c] + (colw[c] - w) / 2
        boxes[s["id"]] = box(left, ys[r] + (rowh[r] - h) / 2, w, h)
    return boxes


def layout(spec, names):
    """Every state's box. The children of a state are placed first, so their
    parent knows its size, then moved inside it."""
    states = spec["states"]
    trs = spec.get("transitions", [])
    by_id = {s["id"]: s for s in states}
    parents = list(dict.fromkeys(s["parent"] for s in states if s.get("parent")))
    leaves = [s for s in states if not pseudo(s) and s["id"] not in parents]
    width = max([MIN_W] + [content_size(s, names)[0] + 2 * PAD_X for s in leaves])
    sizes = {}
    for s in states:
        if pseudo(s) == "initial":
            sizes[s["id"]] = (2 * DOT, 2 * DOT)
        elif pseudo(s) == "final":
            sizes[s["id"]] = (2 * RING + 2, 2 * RING + 2)
        elif s["id"] not in parents:
            sizes[s["id"]] = (width, content_size(s, names)[1] + 2 * PAD_Y + 2)
    inner = {}
    for p in parents:
        kids = [s for s in states if s.get("parent") == p]
        local = grid(kids, sizes, trs, set())
        seen = extent(spec, local, [i for i, tr in enumerate(trs)
                                    if tr["from"] in local and tr["to"] in local])
        x0, y0 = min(q[0] for q in seen), min(q[1] for q in seen)
        x1, y1 = max(q[0] for q in seen), max(q[1] for q in seen)
        cw, ch = content_size(by_id[p], names)
        band = ch + 2 * PAD_Y
        w = max(x1 - x0 + 2 * PAD, cw + 2 * PAD_X)
        dx, dy = (w - (x1 - x0)) / 2 - x0, band + PAD - y0
        inner[p] = ({k: moved(b, dx, dy) for k, b in local.items()}, band)
        sizes[p] = (w, band + y1 - y0 + 2 * PAD)
    boxes = grid([s for s in states if not s.get("parent")], sizes, trs, set(parents))
    for p, (local, band) in inner.items():
        boxes[p]["band"] = band
        for k, b in local.items():
            boxes[k] = moved(b, boxes[p]["l"], boxes[p]["t"])
    return boxes


def extent(spec, boxes, which):
    """The corners of the boxes, and every point and label of the arrows named."""
    seen = []
    for b in boxes.values():
        seen += [(b["l"], b["t"]), (b["r"], b["b"])]
    trs = spec.get("transitions", [])
    lanes = loop_lanes(spec, boxes, which)
    for i in which:
        pts, mid = route(trs[i], boxes, lanes.get(i))
        seen += pts
        text = label_of(trs[i])
        if text and mid:
            w, h = label_size(text)
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
    return seen


def loop_lanes(spec, boxes, which):
    """Give each loop between two states its own distance from the boxes beside
    it, inner loops first. Only states on the same level count."""
    trs = spec.get("transitions", [])
    parent = {s["id"]: s.get("parent") for s in spec["states"]}
    lanes = {}
    for level in {parent[trs[i]["from"]] for i in which}:
        mates = [k for k in boxes if parent.get(k) == level]
        for side in SIDES:
            across = side in ("left", "right")
            loops = [i for i in which if trs[i].get("loop") == side
                     and trs[i]["from"] != trs[i]["to"] and parent[trs[i]["from"]] == level]

            def span(i, across=across):
                a, b = boxes[trs[i]["from"]], boxes[trs[i]["to"]]
                return abs(a["y"] - b["y"]) if across else abs(a["x"] - b["x"])

            offset, last = 0, 0
            for i in sorted(loops, key=span):
                text = label_of(trs[i])
                half = label_size(text)[0 if across else 1] / 2 if text else 4
                offset = half + 22 if not offset else offset + last + half + 14
                last = half
                a, b = boxes[trs[i]["from"]], boxes[trs[i]["to"]]
                if across:
                    lo, hi = sorted((a["y"], b["y"]))
                    near = [boxes[k] for k in mates if boxes[k]["b"] >= lo and boxes[k]["t"] <= hi]
                    base = (min(n["l"] for n in near) if side == "left"
                            else max(n["r"] for n in near))
                else:
                    lo, hi = sorted((a["x"], b["x"]))
                    near = [boxes[k] for k in mates if boxes[k]["r"] >= lo and boxes[k]["l"] <= hi]
                    base = (min(n["t"] for n in near) if side == "above"
                            else max(n["b"] for n in near))
                lanes[i] = base - offset if side in ("left", "above") else base + offset
    return lanes


def route(tr, boxes, lane):
    """The points of one arrow, and the center of its label."""
    a, b = boxes[tr["from"]], boxes[tr["to"]]
    side = tr.get("loop")
    sf, st = shifts(tr)
    text = label_of(tr)
    lw, lh = label_size(text) if text else (0, 0)
    if tr["from"] == tr["to"]:
        side = side or "above"
        d, x, y = LOOP_HALF, a["x"] + sf, a["y"] + sf
        if side == "above":
            pts = [(x - d, a["t"]), (x - d, a["t"] - LOOP), (x + d, a["t"] - LOOP), (x + d, a["t"])]
            return pts, (x, a["t"] - LOOP - 4 - lh / 2)
        if side == "below":
            pts = [(x + d, a["b"]), (x + d, a["b"] + LOOP), (x - d, a["b"] + LOOP), (x - d, a["b"])]
            return pts, (x, a["b"] + LOOP + 4 + lh / 2)
        if side == "left":
            pts = [(a["l"], y + d), (a["l"] - LOOP, y + d), (a["l"] - LOOP, y - d), (a["l"], y - d)]
            return pts, (a["l"] - LOOP - 6 - lw / 2, y)
        pts = [(a["r"], y - d), (a["r"] + LOOP, y - d), (a["r"] + LOOP, y + d), (a["r"], y + d)]
        return pts, (a["r"] + LOOP + 6 + lw / 2, y)
    if side in ("left", "right"):
        sa, sb = (a["l"], b["l"]) if side == "left" else (a["r"], b["r"])
        pts = [(sa, a["y"] + sf), (lane, a["y"] + sf), (lane, b["y"] + st), (sb, b["y"] + st)]
        return pts, (lane, (a["y"] + b["y"]) / 2)
    if side in ("above", "below"):
        sa, sb = (a["t"], b["t"]) if side == "above" else (a["b"], b["b"])
        pts = [(a["x"] + sf, sa), (a["x"] + sf, lane), (b["x"] + st, lane), (b["x"] + st, sb)]
        return pts, ((a["x"] + b["x"]) / 2, lane)
    # Straight, when the two boxes face each other: level with the smaller one.
    apart_x = a["r"] <= b["l"] or b["r"] <= a["l"]
    apart_y = a["b"] <= b["t"] or b["b"] <= a["t"]
    small, big = sorted((a, b), key=lambda q: q["b"] - q["t"])
    if apart_x and big["t"] + 12 <= small["y"] <= big["b"] - 12:
        y = small["y"] + sf
        sa, sb = (a["r"], b["l"]) if b["x"] > a["x"] else (a["l"], b["r"])
        cy = y if not sf else y - 4 - lh / 2 if sf < 0 else y + 4 + lh / 2
        return [(sa, y), (sb, y)], ((sa + sb) / 2, cy)
    small, big = sorted((a, b), key=lambda q: q["r"] - q["l"])
    if apart_y and big["l"] + 16 <= small["x"] <= big["r"] - 16:
        x = small["x"] + sf
        sa, sb = (a["b"], b["t"]) if b["y"] > a["y"] else (a["t"], b["b"])
        cx = x if not sf else x - 6 - lw / 2 if sf < 0 else x + 6 + lw / 2
        return [(x, sa), (x, sb)], (cx, (sa + sb) / 2)
    down, right = b["y"] > a["y"], b["x"] > a["x"]
    kind = tr.get("route", "vhv")
    if kind == "vh":
        sa, sb = a["b"] if down else a["t"], b["l"] if right else b["r"]
        pts = [(a["x"] + sf, sa), (a["x"] + sf, b["y"] + st), (sb, b["y"] + st)]
        return pts, (a["x"] + sf, (sa + b["y"]) / 2)
    if kind == "hv":
        sa, sb = a["r"] if right else a["l"], b["t"] if down else b["b"]
        pts = [(sa, a["y"] + sf), (b["x"] + st, a["y"] + sf), (b["x"] + st, sb)]
        return pts, (b["x"] + st, (a["y"] + sf + sb) / 2)
    sa, sb = (a["b"], b["t"]) if down else (a["t"], b["b"])
    mid = (sa + sb) / 2
    pts = [(a["x"] + sf, sa), (a["x"] + sf, mid), (b["x"] + st, mid), (b["x"] + st, sb)]
    return pts, ((a["x"] + sf + b["x"] + st) / 2, mid)


def travel(spec, boxes, lanes, t):
    """One dot that follows the ticket's path of transitions: the flow's dot."""
    trs = spec["transitions"]
    index = {}
    for i, tr in enumerate(trs):
        index.setdefault((tr["from"], tr["to"]), i)

    def arrow(a, b):
        i = index[(a, b)]
        return route(trs[i], boxes, lanes.get(i))[0], trs[i].get("tone")

    return flow.travel(spec, boxes, lanes, t, arrow)


# Drawing.

def words(s, names, x, y, t, accent):
    """The icon, the small label, the title, and the lines under it, from x, y."""
    title, *sub = s["text"].split("\n")
    name = s.get("icon") or FOR_KIND.get(s.get("kind"), "ticket")
    brow = eyebrow(s, names)
    out = [icon(name, x, y, ICON, accent)]
    if brow:
        out.append(f'<text x="{x + ICON + 8:.1f}" y="{y + 13:.1f}" font-size="{EYEBROW}" '
                   f'font-weight="700" letter-spacing="1.2" fill="{accent}">{escape(brow)}</text>')
    y += ICON + 9
    out.append(f'<text x="{x:.1f}" y="{y + 13:.1f}" font-size="{TITLE}" font-weight="700" '
               f'fill="{t["text"]}">{escape(title)}</text>')
    for j, line in enumerate(sub):
        out.append(f'<text x="{x:.1f}" y="{y + 31 + 17 * j:.1f}" font-size="{SUB}" '
                   f'fill="{t["sub"]}">{escape(line)}</text>')
    return out


def draw_state(s, bx, t, names):
    kind = pseudo(s)
    if kind == "initial":
        return [(f'<g class="initial"><circle cx="{bx["x"]:.1f}" cy="{bx["y"]:.1f}" r="{DOT}" '
                 f'fill="{t["text"]}"/></g>')]
    if kind == "final":
        return [(f'<g class="final"><circle cx="{bx["x"]:.1f}" cy="{bx["y"]:.1f}" r="{RING}" '
                 f'fill="{t["page"]}" stroke="{t["text"]}" stroke-width="2"/>'
                 f'<circle cx="{bx["x"]:.1f}" cy="{bx["y"]:.1f}" r="6" fill="{t["text"]}"/></g>')]
    accent, tint = t["kinds"][s.get("kind", "neutral")]
    l, top, r, b = bx["l"], bx["t"], bx["r"], bx["b"]
    if "band" in bx:
        k, band = PARENT_RADIUS, top + bx["band"]
        return [
            f'<g class="parent" data-state="{escape(s["id"])}">',
            (f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" height="{b - top:.1f}" '
             f'rx="{k}" fill="{tint}" fill-opacity="0.35" stroke="{accent}" stroke-width="1.3"/>'),
            (f'<path d="M{l:.1f},{band:.1f} V{top + k:.1f} Q{l:.1f},{top:.1f} {l + k:.1f},{top:.1f} '
             f'H{r - k:.1f} Q{r:.1f},{top:.1f} {r:.1f},{top + k:.1f} V{band:.1f} Z" fill="{tint}" '
             f'stroke="{accent}" stroke-width="1.3" stroke-linejoin="round"/>'),
            *words(s, names, l + PAD_X, top + PAD_Y, t, accent), "</g>"]
    return [f'<g class="state" data-state="{escape(s["id"])}">',
            (f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" height="{b - top:.1f}" '
             f'rx="{RADIUS}" fill="{tint}" stroke="{accent}" stroke-width="1.3"/>'),
            *words(s, names, l + PAD_X, top + PAD_Y + 1, t, accent), "</g>"]


def whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def number(v):
    return isinstance(v, int | float) and not isinstance(v, bool)


def check_types(spec):
    """Every part of the spec has the type the drawing needs, or a plain message
    says which one does not. A wrong type must not reach the drawing as a crash.
    The error is a ValueError, as for any other bad spec: callers catch that one."""
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")  # noqa: TRY004
    for key in ("title", "desc"):
        if not isinstance(spec.get(key, ""), str):
            raise ValueError(f"the diagram's '{key}' must be text")  # noqa: TRY004
    names = spec.get("names", {})
    if not isinstance(names, dict) or not all(isinstance(v, str) for v in names.values()):
        raise ValueError("'names' must be an object of kind: label, such as "
                         '{"server": "Your machine"}')
    states = spec.get("states", [])
    if not isinstance(states, list) or not all(isinstance(x, dict) for x in states):
        raise ValueError("'states' must be a list of objects")
    for st in states:
        sid = st.get("id")
        if not isinstance(sid, str):
            raise ValueError("every state needs an 'id' that is text")  # noqa: TRY004
        if not whole(st.get("col")) or not whole(st.get("row")):
            raise ValueError(f"state '{sid}' needs a whole number for 'col' and 'row'")
        for key in ("text", "kind", "icon", "parent"):
            if key in st and not isinstance(st[key], str):
                raise ValueError(f"state '{sid}': '{key}' must be text")
        for key in ("initial", "final"):
            if key in st and not isinstance(st[key], bool):
                raise ValueError(f"state '{sid}': '{key}' must be true or false")
    trs = spec.get("transitions", [])
    if not isinstance(trs, list) or not all(isinstance(x, dict) for x in trs):
        raise ValueError("'transitions' must be a list of objects")
    for tr in trs:
        for key in ("from", "to", "event", "guard", "tone", "loop", "route"):
            if key in tr and not isinstance(tr[key], str):
                raise ValueError(f"a transition's '{key}' must be text")
        shift = tr.get("shift", 0)
        if not (number(shift) or (isinstance(shift, list) and len(shift) == 2
                                  and all(number(v) for v in shift))):
            raise ValueError("a transition's shift is a number, or a pair [from, to]")
    ticket = spec.get("ticket")
    if ticket is None:
        return
    if not isinstance(ticket, dict):
        raise ValueError("the ticket must be an object with a path")  # noqa: TRY004
    path = ticket.get("path", [])
    if not isinstance(path, list) or not all(
            isinstance(step, list) and len(step) == 2 and all(isinstance(v, str) for v in step)
            for step in path):
        raise ValueError("the ticket's path must be a list of [from, to] pairs")
    wait = ticket.get("wait", {})
    if not isinstance(wait, dict) or not all(number(v) for v in wait.values()):
        raise ValueError("the ticket's wait must be an object of state: seconds")


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    check_types(spec)
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    states = spec.get("states")
    if not states:
        raise ValueError("the state machine has no states")
    seen = set()
    for s in states:
        if not s["id"]:
            raise ValueError("every state needs an 'id'")
        if s["id"] in seen:
            raise ValueError(f"two states share the id '{s['id']}'")
        seen.add(s["id"])
    by_id = {s["id"]: s for s in states}
    kinds = set(THEMES["light"]["kinds"])
    for s in states:
        sid = s["id"]
        if s.get("initial") and s.get("final"):
            raise ValueError(f"state '{sid}' cannot be both initial and final")
        if not pseudo(s) and not s.get("text"):
            raise ValueError(f"state '{sid}' needs a 'text'")
        if s.get("kind", "neutral") not in kinds:
            raise ValueError(f"state '{sid}': kind must be one of {', '.join(sorted(kinds))}")
        if s.get("icon") and s["icon"] not in ICONS:
            raise ValueError(f"state '{sid}': no icon named '{s['icon']}'")
        p = s.get("parent")
        if p is None:
            continue
        if p not in by_id:
            raise ValueError(f"state '{sid}' is inside '{p}', which is not a state")
        if p == sid:
            raise ValueError(f"state '{sid}' cannot be inside itself")
        if by_id[p].get("parent"):
            raise ValueError(f"state '{sid}' is inside '{p}', which is inside "
                             f"'{by_id[p]['parent']}': nest states one level deep only")
        if pseudo(by_id[p]):
            raise ValueError(f"state '{sid}' is inside '{p}', an {pseudo(by_id[p])} state, "
                             "which cannot hold states")
    cells, starts = {}, {}
    for s in states:
        level = s.get("parent")
        where = (level, s["col"], s["row"])
        if where in cells:
            raise ValueError(f"states '{cells[where]}' and '{s['id']}' share col {s['col']}, "
                             f"row {s['row']}")
        cells[where] = s["id"]
        if s.get("initial"):
            if level in starts:
                place = f"inside '{level}'" if level else "at the top level"
                raise ValueError(f"two initial states {place}: '{starts[level]}' and "
                                 f"'{s['id']}'; keep one")
            starts[level] = s["id"]
    for tr in spec.get("transitions", []):
        for end in ("from", "to"):
            if tr.get(end) not in by_id:
                raise ValueError(f"a transition {end} '{tr.get(end)}', which is not a state")
        if by_id[tr["to"]].get("initial"):
            raise ValueError(f"a transition goes into the initial state '{tr['to']}'")
        if by_id[tr["from"]].get("final"):
            raise ValueError(f"a transition leaves the final state '{tr['from']}'")
        if tr.get("tone") not in (None, "pass", "fail"):
            raise ValueError("a transition's tone must be 'pass' or 'fail'")
        if tr.get("loop") not in (None, *SIDES):
            raise ValueError(f"a transition's loop must be one of {', '.join(SIDES)}")
        if tr.get("route") not in (None, *ROUTES):
            raise ValueError(f"a transition's route must be one of {', '.join(ROUTES)}")
    ticket = spec.get("ticket")
    if ticket is not None:
        if not ticket.get("path"):
            raise ValueError("the ticket has an empty path")
        drawn = {(tr["from"], tr["to"]) for tr in spec.get("transitions", [])}
        for a, b in ticket["path"]:
            if (a, b) not in drawn:
                raise ValueError(f"the ticket's path uses a transition {a} -> {b} "
                                 "that is not drawn")


def draw(spec, theme):
    check(spec)
    t = THEMES[theme]
    names = {k: v.upper() for k, v in (spec.get("names") or {}).items()}
    boxes = layout(spec, names)
    trs = spec.get("transitions", [])
    lanes = loop_lanes(spec, boxes, range(len(trs)))
    seen = []
    for bx in boxes.values():
        seen += [(bx["l"], bx["t"]), (bx["r"], bx["b"])]

    edges, labels = [], []
    for i, tr in enumerate(trs):
        pts, mid = route(tr, boxes, lanes.get(i))
        seen += pts
        tone = tr.get("tone")
        color = t["tones"].get(tone, t["edge"])
        edges.append(f'<path class="transition" d="{rounded(pts)}" fill="none" '
                     f'stroke="{color}" stroke-width="1.6" '
                     f'stroke-linecap="round" stroke-linejoin="round" '
                     f'marker-end="url(#arrow-{tone or "plain"})"/>')
        text = label_of(tr)
        if text:
            w, h = label_size(text)
            ink = t["tones"].get(tone, t["sub"])
            frame = t["tones"].get(tone, t["border"])
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
            labels.append(f'<rect x="{mid[0] - w / 2:.1f}" y="{mid[1] - h / 2:.1f}" '
                          f'width="{w:.1f}" height="{h}" rx="3" fill="{t["page"]}" '
                          f'stroke="{frame}" stroke-width="1"/>')
            labels.append(f'<text x="{mid[0]:.1f}" y="{mid[1] + 3.8:.1f}" text-anchor="middle" '
                          f'font-size="{LABEL}" fill="{ink}">{escape(text)}</text>')

    # Outer states first, so their children and arrows sit on top of them.
    order = sorted(spec["states"], key=lambda s: "band" not in boxes[s["id"]])
    outer = [part for s in order if "band" in boxes[s["id"]]
             for part in draw_state(s, boxes[s["id"]], t, names)]
    body = [part for s in order if "band" not in boxes[s["id"]]
            for part in draw_state(s, boxes[s["id"]], t, names)]
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
    grid_ = (f'<pattern id="grid" x="{x0:.0f}" y="{y0:.0f}" width="24" height="24" '
             f'patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" '
             f'stroke="{t["grid"]}" stroke-width="1"/></pattern>')
    head = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" '
         f'width="{w:.0f}" height="{h:.0f}" role="img" aria-labelledby="title desc" '
         f'font-family="{MONO}">'),
        f'<title id="title">{escape(spec["title"])}</title>',
        f'<desc id="desc">{escape(spec["desc"])}</desc>',
        f'<defs>{"".join(markers)}{grid_}</defs>',
        f"<style>{MOTION}</style>",
        # A full square: no corner is see-through, whatever the page behind it.
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{t["page"]}"/>',
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="url(#grid)"/>',
    ]
    return "\n".join(head + outer + edges + body + labels + ticket + ["</svg>"]) + "\n"
