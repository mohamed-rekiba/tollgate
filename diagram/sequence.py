"""Draw a UML sequence diagram as SVG, in a light and a dark theme.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"type": "sequence",
     "title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "names": {"server": "Your machine"},
     "participants": [{"id": "driver", "text": "The driver\\nOne line under it",
                       "kind": "you" | "ai" | "server" | "check" | "advisor",
                       "icon": "workflow", "tag": "OWN LABEL"}],
     "messages": [{"from": "driver", "to": "gate", "text": "judge the try",
                   "reply": true, "tone": "pass" | "fail", "note": "a small line"}],
     "activations": [{"on": "gate", "from": 2, "to": 5}],
     "frames": [{"kind": "alt" | "loop" | "opt", "from": 3, "to": 6,
                 "label": "until a try passes",
                 "guards": [{"at": 3, "text": "tests pass"}, {"at": 5, "text": "else"}]}],
     "ticket": true}

The design:
- Participants stand in a row across the top, in the order given, each in a
  box in the flat blueprint style of diagram/flow.py: the accent border and
  tint of its kind, its icon, the small label of its kind, and its title. A
  dashed lifeline runs down from each box. "kind", "icon", "tag", and "names"
  work as they do in a flow.
- Messages run down the page in time order, one row each. "text" sits above
  the line in a small framed label. A call is a solid line with a filled
  arrowhead. "reply": true makes a reply: a dashed line with an open
  arrowhead, as in UML. A message whose "from" and "to" are the same
  participant is a self-message: a short loop out to the right and back to
  the same lifeline, with its label beside the loop. "tone" colors the line
  and its label: green for pass, red for fail. "note" adds one small line
  under the arrow.
- "activations" draw a narrow bar on the lifeline of "on", in that
  participant's colors, from the row of message "from" to the row of message
  "to". Messages count from 0. A bar inside another bar on the same lifeline
  sits a little to the right.
- "frames" draw a box around the rows of messages "from" to "to", with a tag
  in its top left corner: "loop" (the messages repeat), "alt" (one of two or
  more ways happens), or "opt" (the messages happen only when the guard
  holds). "label" goes beside the tag. A guard is a condition in brackets; the
  brackets are added when the text has none. A guard "at" the frame's first
  message goes beside the tag. In an alt, each later guard starts a new part
  of the frame, under a dashed line. Frames may nest, but may not cross.
- The gap between two neighboring lifelines is wide enough for the widest
  label that sits in it. A message's label sits in the first gap it crosses.
- "ticket": true sends one dot along the messages, in order. It waits at each
  lifeline it reaches and takes each message's tone. With "reduce motion" set,
  it is hidden.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

from itertools import pairwise
from xml.sax.saxutils import escape

from diagram.flow import LABEL, MONO, MOTION, THEMES, draw_node, node_size, rounded, text_width
from diagram.icons import ICONS

FRAME_KINDS = ("alt", "loop", "opt")
NOTE = 10.5
BAR, NEST = 10, 5           # an activation bar's width; how far a bar inside another moves right
LOOP, SELF_H = 30, 26       # how far a self-message goes out, and how far down it comes back
MIN_W, GAP, MARGIN = 150, 28, 24
LABEL_H, TAG_H = 20, 20
ROW_GAP, FRAME_STEP = 12, 12
SPEED, WAIT, REST = 240, 0.35, 1.4  # pixels a second; seconds at a lifeline; seconds at the end


def label_w(s):
    return text_width(s, LABEL) + 14


def bracket(s):
    s = s.strip()
    return s if s.startswith("[") else f"[{s}]"


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


# The type of each field: (fields that must be there, fields that may be there).
FIELDS = {
    "participant": ({"id": str, "text": str}, {"kind": str, "icon": str, "tag": str}),
    "message": ({"from": str, "to": str, "text": str},
                {"reply": bool, "tone": str, "note": str}),
    "activation": ({"on": str, "from": _is_int, "to": _is_int}, {}),
    "frame": ({"kind": str, "from": _is_int, "to": _is_int}, {"label": str, "guards": list}),
    "guard": ({"at": _is_int, "text": str}, {}),
}
TYPE_WORDS = {str: "words", bool: "true or false", list: "a list", _is_int: "a whole number"}


def _fits(value, want):
    return want(value) if want is _is_int else isinstance(value, want)


def check_types(spec):
    """Stop with a plain message when a part of the spec has the wrong type.

    It raises ValueError, not TypeError: the build and the driver catch
    ValueError as a spec that cannot be drawn."""
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")  # noqa: TRY004
    for key in ("title", "desc"):
        if key in spec and not isinstance(spec[key], str):
            raise ValueError(f"'{key}' must be words")
    names = spec.get("names")
    if names is not None and not (isinstance(names, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in names.items())):
        raise ValueError("'names' must be an object of kind to label, such as "
                         "{\"server\": \"Your machine\"}")
    if "ticket" in spec and not isinstance(spec["ticket"], bool):
        raise ValueError("'ticket' must be true or false")

    def items(key, what, inside):
        found = inside.get(key)
        if found is None:
            return []
        if not isinstance(found, list):
            raise ValueError(f"'{key}' must be a list")  # noqa: TRY004
        for i, item in enumerate(found):
            if not isinstance(item, dict):
                raise ValueError(f"{what} {i} must be an object")  # noqa: TRY004
            need, may = FIELDS[what]
            for field in need:
                if field not in item:
                    raise ValueError(f"{what} {i} needs '{field}'")
            for field, want in {**need, **may}.items():
                if field in item and not _fits(item[field], want):
                    raise ValueError(f"{what} {i}: '{field}' must be {TYPE_WORDS[want]}")
        return found

    items("participants", "participant", spec)
    items("messages", "message", spec)
    items("activations", "activation", spec)
    for f in items("frames", "frame", spec):
        items("guards", "guard", f)


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    check_types(spec)
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    people = spec.get("participants")
    if not people:
        raise ValueError("the sequence diagram has no participants")
    kinds = set(THEMES["light"]["kinds"])
    ids = []
    for p in people:
        if not p["id"] or not p["text"]:
            raise ValueError("each participant needs an 'id' and a 'text'")
        if p.get("kind", "neutral") not in kinds:
            raise ValueError(f"participant '{p['id']}': kind must be one of "
                             f"{', '.join(sorted(kinds))}")
        if p.get("icon") and p["icon"] not in ICONS:
            raise ValueError(f"participant '{p['id']}': no icon named '{p['icon']}'")
        ids.append(p["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("two participants share an id")
    for k in spec.get("names") or {}:
        if k not in kinds:
            raise ValueError(f"'names' renames '{k}', which is not a kind")
    messages = spec.get("messages") or []
    for i, m in enumerate(messages):
        for end in ("from", "to"):
            if m.get(end) not in ids:
                raise ValueError(f"message {i} goes {end} '{m.get(end)}', which is not a "
                                 "participant")
        if not m.get("text"):
            raise ValueError(f"message {i} has no text")
        if m.get("tone") not in (None, "pass", "fail"):
            raise ValueError(f"message {i}: tone must be 'pass' or 'fail'")
    count = len(messages)

    def rows(what, a, b):
        if not (isinstance(a, int) and isinstance(b, int)) or not 0 <= a <= b < count:
            raise ValueError(f"{what} runs from message {a} to message {b}, but the messages "
                             f"are numbered 0 to {count - 1}")

    for a in spec.get("activations") or []:
        if a.get("on") not in ids:
            raise ValueError(f"an activation is on '{a.get('on')}', which is not a participant")
        rows(f"the activation on '{a['on']}'", a.get("from"), a.get("to"))
    frames = spec.get("frames") or []
    for i, f in enumerate(frames):
        if f.get("kind") not in FRAME_KINDS:
            raise ValueError(f"frame {i}: kind must be one of {', '.join(FRAME_KINDS)}")
        rows(f"frame {i}", f.get("from"), f.get("to"))
        ats = [g.get("at") for g in f.get("guards") or []]
        for at in ats:
            if not isinstance(at, int) or not f["from"] <= at <= f["to"]:
                raise ValueError(f"frame {i} has a guard at message {at}, outside the frame")
        if len(ats) != len(set(ats)):
            raise ValueError(f"frame {i} has two guards at one message")
        if f["kind"] != "alt" and any(at != f["from"] for at in ats):
            raise ValueError(f"frame {i}: only an alt has more than one part; a {f['kind']} "
                             "has one guard, at its first message")
    for i, f in enumerate(frames):
        for j, g in enumerate(frames[i + 1:], i + 1):
            apart = f["to"] < g["from"] or g["to"] < f["from"]
            inside = (f["from"] <= g["from"] and g["to"] <= f["to"]) or \
                     (g["from"] <= f["from"] and f["to"] <= g["to"])
            if not (apart or inside):
                raise ValueError(f"frames {i} and {j} cross; a frame must hold another whole")
    if spec.get("ticket") and not messages:
        raise ValueError("the ticket has no messages to follow")


def inner_first(frames):
    """Frame indexes, each after every frame it holds."""
    return sorted(range(len(frames)), key=lambda k: (frames[k]["to"] - frames[k]["from"], -k))


def holds(f, g):
    return f is not g and f["from"] <= g["from"] and g["to"] <= f["to"]


def tag_w(f):
    return text_width(f["kind"], LABEL) + 16


def head_text(f):
    """The words beside a frame's tag: its label, then the guard at its first row."""
    parts = [f.get("label", "")]
    parts += [bracket(g["text"]) for g in f.get("guards") or [] if g["at"] == f["from"]]
    return " ".join(p for p in parts if p)


def later_guards(f):
    return sorted((g for g in f.get("guards") or [] if g["at"] != f["from"]), key=lambda g: g["at"])


def layout(spec):
    """Where everything goes: lifeline x, rows, bars, and frames."""
    people = spec["participants"]
    messages = spec.get("messages") or []
    frames = spec.get("frames") or []
    col = {p["id"]: i for i, p in enumerate(people)}
    n = len(people)
    sizes = [node_size(dict(p, shape="step")) for p in people]
    box_w = max(MIN_W, *(w for w, _ in sizes))
    box_h = max(h for _, h in sizes)
    need = [box_w + GAP] * max(n - 1, 0)
    right_room = BAR / 2 + NEST + 12  # room right of the last lifeline
    side = BAR + 2 * NEST + 28        # a label's room from the two lifelines beside it

    def room(c, width):
        nonlocal right_room
        if c < n - 1:
            need[c] = max(need[c], width)
        else:
            right_room = max(right_room, width)

    for m in messages:
        a, b = col[m["from"]], col[m["to"]]
        w = max(label_w(m["text"]), text_width(m.get("note", ""), NOTE))
        if a == b:
            room(a, BAR / 2 + NEST + LOOP + 10 + w + 14 + BAR / 2)
        else:
            need[min(a, b) if a < b else a - 1] = max(need[min(a, b) if a < b else a - 1],
                                                      w + side)

    # Frames: the lifelines each one spans, and its room left and right of them.
    spans, pad_l, pad_r = {}, {}, {}
    for k in inner_first(frames):
        f = frames[k]
        used = {col[m[e]] for m in messages[f["from"]:f["to"] + 1] for e in ("from", "to")}
        inner = [j for j in range(len(frames)) if holds(f, frames[j]) and j != k]
        for j in inner:
            used |= set(range(spans[j][0], spans[j][1] + 1))
        lo, hi = min(used), max(used)
        spans[k] = (lo, hi)
        pad_l[k] = max([tag_w(f) + 8 + BAR / 2 + NEST]
                       + [pad_l[j] + FRAME_STEP for j in inner if spans[j][0] == lo])
        texts = [head_text(f)] + [bracket(g["text"]) for g in later_guards(f)]
        words = BAR / 2 + NEST + 10 + max(text_width(s, LABEL) for s in texts) + 12
        right = [BAR / 2 + NEST + 12] + [pad_r[j] + FRAME_STEP for j in inner if spans[j][1] == hi]
        for m in messages[f["from"]:f["to"] + 1]:
            if m["from"] == m["to"] and col[m["from"]] == hi:
                w = max(label_w(m["text"]), text_width(m.get("note", ""), NOTE))
                right.append(BAR / 2 + NEST + LOOP + 10 + w + 12)
        if lo == hi:
            right.append(words)
        elif lo < n - 1:
            need[lo] = max(need[lo], words + BAR / 2 + NEST)
        pad_r[k] = max(right)
        if lo > 0:
            need[lo - 1] = max(need[lo - 1], pad_l[k] + BAR / 2 + NEST + 12)
        room(hi, pad_r[k] + (BAR / 2 + NEST + 12 if hi < n - 1 else 0))

    xs = [0.0]
    for d in need:
        xs.append(xs[-1] + d)

    # Rows, top to bottom.
    rows = []
    y = box_h + 24
    frame_top, frame_bottom, dividers = {}, {}, []
    for i, m in enumerate(messages):
        starting = sorted((k for k, f in enumerate(frames) if f["from"] == i),
                          key=lambda k: (frames[k]["from"] - frames[k]["to"], k))
        for k in starting:
            frame_top[k] = y
            y += TAG_H + 8
        for k, f in enumerate(frames):
            for g in later_guards(f):
                if g["at"] == i:
                    y += 4
                    dividers.append((k, y, bracket(g["text"])))
                    y += 24
        if m["from"] == m["to"]:
            top = y
            line = top + 6
            back = line + SELF_H
            bottom = back + 8 + (14 if m.get("note") else 0)
        else:
            top = y
            line = top + LABEL_H + 7
            back = line
            bottom = line + (20 if m.get("note") else 8)
        rows.append({"top": top, "y": line, "y2": back, "bottom": bottom})
        y = bottom
        ending = sorted((k for k, f in enumerate(frames) if f["to"] == i),
                        key=lambda k: (frames[k]["to"] - frames[k]["from"], -k))
        for k in ending:
            y += 8
            frame_bottom[k] = y
        y += ROW_GAP

    # Activation bars, each a little right of any bar it sits in.
    bars = []
    for a in spec.get("activations") or []:
        depth = sum(1 for b in bars if b["on"] == a["on"]
                    and b["from"] <= a["from"] and a["to"] <= b["to"])
        cx = xs[col[a["on"]]] + depth * NEST
        bars.append({"on": a["on"], "from": a["from"], "to": a["to"], "x": cx,
                     "top": rows[a["from"]]["y"] - 6, "bottom": rows[a["to"]]["y2"] + 6})

    boxes = []
    for i in range(n):
        left = xs[i] - box_w / 2
        boxes.append({"l": left, "r": left + box_w, "t": 0.0, "b": box_h,
                      "x": xs[i], "y": box_h / 2})
    out_frames = []
    for k, f in enumerate(frames):
        lo, hi = spans[k]
        out_frames.append({"l": xs[lo] - pad_l[k], "r": xs[hi] + pad_r[k], "lo": lo,
                           "t": frame_top[k], "b": frame_bottom[k]})
    return {"xs": xs, "col": col, "rows": rows, "bars": bars, "boxes": boxes,
            "frames": out_frames, "dividers": dividers, "end": y + 8, "right_room": right_room}


def edge(lay, who, i, y, toward):
    """Where a message at row i meets the lifeline of `who`: the side of its bar
    that faces `toward` (+1 right, -1 left), or the lifeline itself."""
    x = lay["xs"][lay["col"][who]]
    on = [b for b in lay["bars"] if b["on"] == who and b["top"] <= y <= b["bottom"]]
    if not on:
        return x
    if toward > 0:
        return max(b["x"] for b in on) + BAR / 2
    return min(b["x"] for b in on) - BAR / 2


def points(lay, m, i):
    """The points of message i's line."""
    r = lay["rows"][i]
    col = lay["col"]
    if m["from"] == m["to"]:
        sx = edge(lay, m["from"], i, r["y"], 1)
        ex = edge(lay, m["from"], i, r["y2"], 1)
        out = max(sx, ex) + LOOP
        return [(sx, r["y"]), (out, r["y"]), (out, r["y2"]), (ex, r["y2"])]
    way = 1 if col[m["to"]] > col[m["from"]] else -1
    return [(edge(lay, m["from"], i, r["y"], way), r["y"]),
            (edge(lay, m["to"], i, r["y"], -way), r["y"])]


def travel(spec, lay, t):
    """One dot that follows the messages in order, then starts again.

    It runs along each message, waits where the message reaches its lifeline,
    and jumps to the start of the next message."""
    base = t["kinds"]["ai"][0]
    pts, marks, colors = [], [], []
    now, dist = 0.0, 0.0
    for i, m in enumerate(spec["messages"]):
        line = points(lay, m, i)
        if pts:
            dist += abs(line[0][0] - pts[-1][0]) + abs(line[0][1] - pts[-1][1])
        pts += line
        marks.append((now, dist))
        colors.append((now, t["tones"].get(m.get("tone"), base)))
        if i == 0:
            now += WAIT
            marks.append((now, dist))
        for (x0, y0), (x1, y1) in pairwise(line):
            step = abs(x1 - x0) + abs(y1 - y0)
            dist += step
            now += step / SPEED
            marks.append((now, dist))
        now += WAIT
        marks.append((now, dist))
    now += REST
    marks.append((now, dist))
    dur, total = now, dist or 1
    key_times = ";".join(f"{a / dur:.4f}" for a, _ in marks)
    key_points = ";".join(f"{d / total:.4f}" for _, d in marks)
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    shared = f'dur="{dur:.2f}s" repeatCount="indefinite"'
    fill = (f'<animate attributeName="fill" values="{";".join(c for _, c in colors)}" '
            f'keyTimes="{";".join(f"{a / dur:.4f}" for a, _ in colors)}" calcMode="discrete" '
            f'{shared}/>')
    return ['<g class="ticket">',
            f'<circle r="13" fill="{base}" opacity="0.2">{fill}</circle>',
            f'<circle r="6.5" fill="{base}" stroke="{t["page"]}" stroke-width="2">{fill}</circle>',
            (f'<animateMotion path="{path}" keyPoints="{key_points}" keyTimes="{key_times}" '
             f'calcMode="linear" {shared}/>'),
            "</g>"]


def framed_label(x, y, text, ink, frame, t, n, anchor="middle"):
    """A small framed label; x is its center, or its left with anchor start."""
    w = label_w(text)
    left = x - w / 2 if anchor == "middle" else x
    rect = (f'<rect x="{left:.1f}" y="{y:.1f}" width="{w:.1f}" height="{LABEL_H}" rx="3" '
            f'fill="{t["page"]}" stroke="{frame}" stroke-width="1"/>')
    words = (f'<text x="{left + w / 2:.1f}" y="{y + LABEL_H / 2 + 3.8:.1f}" text-anchor="middle" '
             f'font-size="{LABEL}" fill="{ink}">{escape(text)}</text>')
    return [f'<g class="label" data-n="{n}">', rect, words, "</g>"], (left, y, left + w, y + LABEL_H)


def draw(spec, theme):
    check(spec)
    t = THEMES[theme]
    names = {k: v.upper() for k, v in (spec.get("names") or {}).items()}
    people = [dict(p, shape="step", kind_name=names[p["kind"]]) if p.get("kind") in names
              else dict(p, shape="step") for p in spec["participants"]]
    messages = spec.get("messages") or []
    lay = layout(spec)
    xs, rows = lay["xs"], lay["rows"]
    seen = [(b["l"], b["t"]) for b in lay["boxes"]] + [(b["r"], b["b"]) for b in lay["boxes"]]
    seen += [(xs[-1] + lay["right_room"], lay["end"])]

    frames = []
    for k, (f, box) in enumerate(zip(spec.get("frames") or [], lay["frames"], strict=True)):
        l, r, top, b = box["l"], box["r"], box["t"], box["b"]
        seen += [(l, top), (r, b)]
        w = tag_w(f)
        frames.append(f'<g class="frame" data-kind="{f["kind"]}" data-n="{k}">')
        frames.append(f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" height="{b - top:.1f}" '
                      f'rx="2" fill="none" stroke="{t["edge"]}" stroke-width="1.3"/>')
        frames.append(f'<polygon points="{l:.1f},{top:.1f} {l + w:.1f},{top:.1f} '
                      f'{l + w:.1f},{top + TAG_H - 6:.1f} {l + w - 6:.1f},{top + TAG_H:.1f} '
                      f'{l:.1f},{top + TAG_H:.1f}" fill="{t["kinds"]["neutral"][1]}" '
                      f'stroke="{t["edge"]}" stroke-width="1.3" stroke-linejoin="round"/>')
        frames.append(f'<text x="{l + 7:.1f}" y="{top + 14:.1f}" font-size="{LABEL}" '
                      f'font-weight="700" fill="{t["text"]}">{escape(f["kind"])}</text>')
        words = head_text(f)
        x = xs[box["lo"]] + BAR / 2 + NEST + 10
        if words:
            frames.append(f'<text x="{x:.1f}" y="{top + 14:.1f}" font-size="{LABEL}" '
                          f'fill="{t["sub"]}">{escape(words)}</text>')
        for j, y, text in lay["dividers"]:
            if j == k:
                frames.append(f'<path class="divider" d="M{l:.1f},{y:.1f} H{r:.1f}" '
                              f'stroke="{t["edge"]}" stroke-width="1.2" stroke-dasharray="6 4"/>')
                frames.append(f'<text x="{x:.1f}" y="{y + 16:.1f}" font-size="{LABEL}" '
                              f'fill="{t["sub"]}">{escape(text)}</text>')
        frames.append("</g>")

    lines = []
    for p, x in zip(people, xs, strict=True):
        lines.append(f'<line class="lifeline" data-of="{escape(p["id"])}" x1="{x:.1f}" '
                     f'y1="{lay["boxes"][0]["b"]:.1f}" x2="{x:.1f}" y2="{lay["end"]:.1f}" '
                     f'stroke="{t["edge"]}" stroke-width="1.2" stroke-dasharray="4 4"/>')
    kinds = {p["id"]: p.get("kind", "neutral") for p in people}
    for b in lay["bars"]:
        accent, tint = t["kinds"][kinds[b["on"]]]
        lines.append(f'<rect class="activation" data-on="{escape(b["on"])}" '
                     f'x="{b["x"] - BAR / 2:.1f}" y="{b["top"]:.1f}" width="{BAR}" '
                     f'height="{b["bottom"] - b["top"]:.1f}" fill="{tint}" stroke="{accent}" '
                     f'stroke-width="1.3"/>')

    arrows, labels = [], []
    for i, m in enumerate(messages):
        pts = points(lay, m, i)
        r = rows[i]
        tone = m.get("tone")
        color = t["tones"].get(tone, t["edge"])
        reply = bool(m.get("reply"))
        dash = ' stroke-dasharray="6 4"' if reply else ""
        head = f'{"open" if reply else "arrow"}-{tone or "plain"}'
        arrows.append(f'<path class="message {"reply" if reply else "call"}" data-n="{i}" '
                      f'data-from="{escape(m["from"])}" data-to="{escape(m["to"])}" '
                      f'd="{rounded(pts, 6)}" fill="none" stroke="{color}" stroke-width="1.6" '
                      f'stroke-linejoin="round"{dash} marker-end="url(#{head})"/>')
        seen += pts
        ink = t["tones"].get(tone, t["text"])
        frame = t["tones"].get(tone, t["border"])
        if m["from"] == m["to"]:
            lx = pts[1][0] + 10
            ly = (r["y"] + r["y2"]) / 2 - LABEL_H / 2
            out, area = framed_label(lx, ly, m["text"], ink, frame, t, i, anchor="start")
            note_x, note_y, anchor = lx, r["y2"] + 18, "start"
        else:
            a, b = lay["col"][m["from"]], lay["col"][m["to"]]
            g = a if b > a else a - 1
            cx = (xs[g] + xs[g + 1]) / 2
            out, area = framed_label(cx, r["y"] - 7 - LABEL_H, m["text"], ink, frame, t, i)
            note_x, note_y, anchor = cx, r["y"] + 15, "middle"
        labels += out
        seen += [area[:2], area[2:]]
        if m.get("note"):
            labels.append(f'<text class="note" x="{note_x:.1f}" y="{note_y:.1f}" '
                          f'text-anchor="{anchor}" font-size="{NOTE}" fill="{t["sub"]}">'
                          f'{escape(m["note"])}</text>')
            nw = text_width(m["note"], NOTE)
            left = note_x - nw / 2 if anchor == "middle" else note_x
            seen += [(left, note_y - 10), (left + nw, note_y + 3)]

    body = []
    for i, (p, bx) in enumerate(zip(people, lay["boxes"], strict=True)):
        body.append(f'<g class="participant" data-of="{escape(p["id"])}">')
        body += draw_node(p, bx, t, i)
        body.append("</g>")
    ticket = travel(spec, lay, t) if spec.get("ticket") else []

    x0 = min(p[0] for p in seen) - MARGIN
    y0 = min(p[1] for p in seen) - MARGIN
    x1 = max(p[0] for p in seen) + MARGIN
    y1 = max(p[1] for p in seen) + MARGIN
    w, h = x1 - x0, y1 - y0
    markers = []
    for name, color in [("plain", t["edge"])] + list(t["tones"].items()):
        markers.append(f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                       f'markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" '
                       f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9 z" '
                       f'fill="{color}"/></marker>')
        markers.append(f'<marker id="open-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                       f'markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" '
                       f'orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" '
                       f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
                       f'stroke-linejoin="round"/></marker>')
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
    return "\n".join(head + frames + lines + arrows + labels + body + ticket + ["</svg>"]) + "\n"
