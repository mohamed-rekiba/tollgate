"""Draw a UML class diagram or an entity relationship (ER) diagram as SVG, in a
light and a dark theme: the flat blueprint style.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A class diagram is a dict, often read from JSON:

    {"type": "class",
     "title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "names": {"server": "The store"},
     "classes": [{"id": "plan", "name": "Plan", "col": 0, "row": 0,
                  "stereotype": "dataclass", "abstract": false,
                  "fields": ["id: str", "tickets: list"],
                  "methods": ["parse(text) Plan"],
                  "kind": "you" | "ai" | "server" | "check" | "advisor",
                  "icon": "plan"}],
     "relations": [{"from": "plan", "to": "ticket",
                    "type": "inherits" | "implements" | "owns" | "composition" |
                            "has" | "aggregation" | "association" | "uses" | "dependency",
                    "ends": ["1", "1..*"], "roles": ["", "tickets"],
                    "label": "lists", "arrow": true,
                    "loop": "left" | "right" | "above" | "below",
                    "route": "vhv" | "vh" | "hv", "shift": 12}]}

An ER diagram:

    {"type": "er",
     "title": "...", "desc": "...", "names": {"server": "The store"},
     "tables": [{"id": "lock", "name": "locks", "col": 0, "row": 0,
                 "kind": "server", "icon": "lock",
                 "columns": [{"name": "ticket", "type": "text", "key": "pk" | "fk" | "pk fk"},
                             {"name": "commit", "type": "commit"}]}],
     "relations": [{"from": "pass", "to": "lock",
                    "ends": ["zero or many", "exactly one"],
                    "label": "made under",
                    "loop": "...", "route": "...", "shift": 12}]}

The design follows UML and the crow's foot notation, drawn in Tollgate's style:
- A fine grid behind everything, monospace type, the same colors as a flow.
  "kind" sets a box's color, its icon, and the small label over its name (YOU,
  AI, SERVER, CHECK, ADVISOR); "names" renames those labels for the whole
  diagram. "icon" picks another icon from diagram/icons.py. A box with no kind
  is neutral slate and has no icon unless "icon" names one; a table's icon is
  a database by default.
- A class is a box in three compartments: its name, its fields, its methods.
  Leave out "fields" or "methods" and that compartment is not drawn; an empty
  list draws it empty. "stereotype" goes over the name in guillemets, such as
  «interface». "abstract": true sets the name in italics. Write each field and
  method as the reader would type it.
- A table is a box with its name, then one row for each column: its name, and
  its type on the right. "key" marks a primary key PK, a foreign key FK, or
  both ("pk fk") with small tags on the left.
- Boxes sit on a grid of columns and rows. The boxes of a column share its
  width, and each row is as tall as its tallest box. The gaps grow to fit the
  labels and the ends.
- A relation is a line between two boxes: straight when they face each other,
  otherwise it bends at right angles with round corners. "route", "loop", and
  "shift" work as in a state machine (diagram/state.py): "route" picks the
  bends, "loop" sends the line out to one side in its own lane, and "shift"
  moves its ends along the sides, so two lines can share a side. A relation
  from a box to itself is a small loop. "label" sits in the middle of the line.
- Read a class relation as a sentence, "from" first: a circle inherits a
  shape, a canvas owns its layers. The ends follow UML:
  inherits      solid line, a hollow triangle at "to" (the parent)
  implements    dashed line, a hollow triangle at "to" (the interface)
  owns          solid line, a filled diamond at "from" (the whole), also
                called composition: the parts live and die with it
  has           solid line, a hollow diamond at "from" (the whole), also
                called aggregation: the parts live on their own
  association   solid line, no end; "arrow": true adds an open arrow at "to"
  uses          dashed line, an open arrow at "to", also called dependency
  "ends" puts the multiplicity by each end, such as ["1", "0..*"], and
  "roles" a role name before it, such as ["", "layers"]. Either may be "".
- An ER relation has a crow's foot end at each box. "ends" names them, the
  end at "from" first: "exactly one" (two bars), "zero or one" (a ring and a
  bar), "one or many" (a bar and a crow's foot), "zero or many" (a ring and a
  crow's foot). "one" and "many" are short for "exactly one" and "zero or many".
- Lines are still: nothing moves.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

from xml.sax.saxutils import escape

from diagram import state
from diagram.flow import (
    EYEBROW,
    ICON,
    KIND_NAMES,
    LABEL,
    MARGIN,
    MONO,
    PAD_X,
    PAD_Y,
    SUB,
    THEMES,
    TITLE,
    rounded,
    text_width,
)
from diagram.icons import FOR_KIND, ICONS, icon

GAP_X, GAP_Y = 72, 64
MIN_W = 150
PITCH, ROW = 17, 20                  # a field or method line; a table's row
TAG_W, TAG_H, TAG = 21, 14, 9        # a PK or FK tag, and its font size
END_GAP = 6                          # from a box's side to the words by an end
SELF, SELF_HALF = 44, 30             # a relation to its own box: how far out, half its width


# The ends of a line, shared by both kinds: name -> (length along the line,
# height, the drawing). Each is drawn pointing right, into a box whose side is
# at x = length; the marker turns it to fit the line at either end. In a
# drawing, {ink} is the line's color and {page} the page, which hides the line
# under a hollow shape.
ENDS = {
    "triangle": (16, 14, ('<path d="M1,1 L15,7 L1,13 Z" fill="{page}" stroke="{ink}" '
                          'stroke-width="1.4" stroke-linejoin="round"/>')),
    "arrow": (14, 14, ('<path d="M2,2 L13,7 L2,12" fill="none" stroke="{ink}" stroke-width="1.6" '
                       'stroke-linecap="round" stroke-linejoin="round"/>')),
    "diamond": (22, 12, ('<path d="M1,6 L11,1 L21,6 L11,11 Z" fill="{ink}" stroke="{ink}" '
                         'stroke-width="1.4" stroke-linejoin="round"/>')),
    "open diamond": (22, 12, ('<path d="M1,6 L11,1 L21,6 L11,11 Z" fill="{page}" stroke="{ink}" '
                              'stroke-width="1.4" stroke-linejoin="round"/>')),
    "exactly one": (26, 18, ('<path d="M14,2 V16 M19,2 V16" fill="none" stroke="{ink}" '
                             'stroke-width="1.5"/>')),
    "zero or one": (26, 18, ('<circle cx="9" cy="9" r="4" fill="{page}" stroke="{ink}" '
                             'stroke-width="1.5"/><path d="M19,2 V16" fill="none" stroke="{ink}" '
                             'stroke-width="1.5"/>')),
    "one or many": (26, 18, ('<path d="M8,2 V16 M13,9 L26,2 M13,9 L26,16 M13,9 H26" fill="none" '
                             'stroke="{ink}" stroke-width="1.5"/>')),
    "zero or many": (26, 18, ('<circle cx="6" cy="9" r="4" fill="{page}" stroke="{ink}" '
                              'stroke-width="1.5"/><path d="M13,9 L26,2 M13,9 L26,16 M13,9 H26" '
                              'fill="none" stroke="{ink}" stroke-width="1.5"/>')),
}
CROWS_FEET = ("exactly one", "zero or one", "one or many", "zero or many")
SHORT = {"one": "exactly one", "many": "zero or many"}

# A class relation -> (dashed, the end at "from", the end at "to").
RELATIONS = {
    "inherits": (False, None, "triangle"),
    "implements": (True, None, "triangle"),
    "owns": (False, "diamond", None),
    "composition": (False, "diamond", None),
    "has": (False, "open diamond", None),
    "aggregation": (False, "open diamond", None),
    "association": (False, None, None),
    "uses": (True, None, "arrow"),
    "dependency": (True, None, "arrow"),
}


def marker_id(name):
    return "end-" + name.replace(" ", "-")


def markers(t):
    out = []
    for name, (length, height, art) in ENDS.items():
        out.append(f'<marker id="{marker_id(name)}" data-end="{name}" '
                   f'viewBox="0 0 {length} {height}" refX="{length}" refY="{height / 2:g}" '
                   f'markerWidth="{length}" markerHeight="{height}" markerUnits="userSpaceOnUse" '
                   f'orient="auto-start-reverse">'
                   f'{art.format(ink=t["edge"], page=t["page"])}</marker>')
    return out


def line_style(spec, rel):
    """(dashed, end at "from", end at "to") of one relation."""
    if spec["type"] == "er":
        a, b = (SHORT.get(e, e) for e in rel["ends"])
        return False, a, b
    dashed, a, b = RELATIONS[rel.get("type", "association")]
    if rel.get("type", "association") == "association" and rel.get("arrow"):
        b = "arrow"
    return dashed, a, b


def end_words(spec, rel):
    """The words by each end of a class relation: the role, then the multiplicity."""
    if spec["type"] == "er":
        return "", ""
    ends = rel.get("ends") or ["", ""]
    roles = rel.get("roles") or ["", ""]
    return tuple(" ".join(p for p in (r, e) if p) for r, e in zip(roles, ends, strict=True))


# The boxes.

def boxes_of(spec):
    return spec["classes"] if spec["type"] == "class" else spec["tables"]


def eyebrow(b, names):
    kind = b.get("kind")
    return names.get(kind) or KIND_NAMES.get(kind, "")


def icon_of(spec, b):
    if b.get("icon"):
        return b["icon"]
    if spec["type"] == "er":
        return "database"
    return FOR_KIND.get(b.get("kind"))


def stereotype(b):
    return f"«{b['stereotype']}»" if b.get("stereotype") else ""


def tags(col):
    return [k.upper() for k in (col.get("key") or "").split()]


def tag_room(table):
    most = max((len(tags(c)) for c in table["columns"]), default=0)
    return most * (TAG_W + 4) + (4 if most else 0)


def head_size(spec, b, names):
    """The width and height of the words in a box's top compartment."""
    w, h = text_width(b["name"], TITLE), 18
    brow = eyebrow(b, names)
    if icon_of(spec, b):
        w = max(w, ICON + (8 + text_width(brow, EYEBROW, 1.2) if brow else 0))
        h += ICON + 8
    if stereotype(b):
        w, h = max(w, text_width(stereotype(b), SUB)), h + PITCH
    return w, h


def compartments(b):
    return [b[k] for k in ("fields", "methods") if k in b]


def size(spec, b, names):
    w, h = head_size(spec, b, names)
    h += 2 * PAD_Y
    if spec["type"] == "class":
        for lines in compartments(b):
            w = max([w] + [text_width(x, SUB) for x in lines])
            h += 8 + PITCH * len(lines) + 6
    else:
        cols = b["columns"]
        names_w = max((text_width(c["name"], SUB) for c in cols), default=0)
        types_w = max((text_width(c.get("type", ""), SUB) for c in cols), default=0)
        w = max(w, tag_room(b) + names_w + (24 + types_w if types_w else 0))
        h += 6 + ROW * len(cols) + 4
    return max(MIN_W, w + 2 * PAD_X), h


def rel_of(rel):
    """A relation as a state machine's transition, so its routes and lanes serve."""
    out = {k: rel[k] for k in ("from", "to", "loop", "route", "shift") if k in rel}
    if rel.get("label"):
        out["event"] = rel["label"]
    return out


def end_room(spec, rel, which):
    """How far an end reaches along its line: its marker, and the words beside it."""
    i = 0 if which == "from" else 1
    _, *ends = line_style(spec, rel)
    marker = ENDS[ends[i]][0] if ends[i] else 0
    words = end_words(spec, rel)[i]
    return max(marker + 8, END_GAP + text_width(words, LABEL) + 6 if words else 0, 18)


def layout(spec, names):
    items = boxes_of(spec)
    sizes = {b["id"]: size(spec, b, names) for b in items}
    where = {b["id"]: (b["col"], b["row"]) for b in items}
    cols = sorted({c for c, _ in where.values()})
    rows = sorted({r for _, r in where.values()})
    colw = {c: max(sizes[b["id"]][0] for b in items if b["col"] == c) for c in cols}
    rowh = {r: max(sizes[b["id"]][1] for b in items if b["row"] == r) for r in rows}
    col_need, row_need = {}, {}

    def need(d, k, v):
        d[k] = max(d.get(k, 0), v)

    for rel in spec.get("relations", []):
        (c1, r1), (c2, r2) = where[rel["from"]], where[rel["to"]]
        label = rel.get("label", "")
        lw, lh = state.label_size(label) if label else (0, 0)
        if rel["from"] == rel["to"]:
            side = rel.get("loop", "above")
            if side in ("above", "below"):
                k = r1 if side == "below" else rows[max(rows.index(r1) - 1, 0)]
                need(row_need, k, SELF + lh + 24)
            else:
                k = c1 if side == "right" else cols[max(cols.index(c1) - 1, 0)]
                need(col_need, k, SELF + lw + 20)
            continue
        if rel.get("loop"):
            continue
        a, b = end_room(spec, rel, "from"), end_room(spec, rel, "to")
        if r1 == r2:
            need(col_need, min(c1, c2), a + b + (lw + 16 if lw else 0))
        else:
            # The words by the ends sit beside the line, above and below the label.
            need(row_need, min(r1, r2), 2 * 24 + (lh + 16 if lh else 8))
    xs, x = {}, 0
    for c in cols:
        xs[c] = x
        x += colw[c] + max(GAP_X, col_need.get(c, 0))
    ys, y = {}, 0
    for r in rows:
        ys[r] = y
        y += rowh[r] + max(GAP_Y, row_need.get(r, 0))
    out = {}
    for b in items:
        c, r = b["col"], b["row"]
        h = sizes[b["id"]][1]
        out[b["id"]] = state.box(xs[c], ys[r] + (rowh[r] - h) / 2, colw[c], h)
    return out


def route(rel, tr, boxes, lane):
    """The points of one line, and the center of its label. A relation from a box
    to itself is a loop wide enough for an end on each leg."""
    if rel["from"] != rel["to"]:
        return state.route(tr, boxes, lane)
    a = boxes[rel["from"]]
    side = rel.get("loop", "above")
    sf, _ = state.shifts(tr)
    d, x, y = SELF_HALF, a["x"] + sf, a["y"] + sf
    lw, lh = state.label_size(rel["label"]) if rel.get("label") else (0, 0)
    if side == "above":
        return ([(x - d, a["t"]), (x - d, a["t"] - SELF), (x + d, a["t"] - SELF), (x + d, a["t"])],
                (x, a["t"] - SELF - 4 - lh / 2))
    if side == "below":
        return ([(x + d, a["b"]), (x + d, a["b"] + SELF), (x - d, a["b"] + SELF), (x - d, a["b"])],
                (x, a["b"] + SELF + 4 + lh / 2))
    if side == "left":
        return ([(a["l"], y + d), (a["l"] - SELF, y + d), (a["l"] - SELF, y - d), (a["l"], y - d)],
                (a["l"] - SELF - 6 - lw / 2, y))
    return ([(a["r"], y - d), (a["r"] + SELF, y - d), (a["r"] + SELF, y + d), (a["r"], y + d)],
            (a["r"] + SELF + 6 + lw / 2, y))


# Drawing.

def draw_head(spec, b, bx, t, names, accent):
    x, y = bx["l"] + PAD_X, bx["t"] + PAD_Y
    out = []
    name = icon_of(spec, b)
    if name:
        out.append(icon(name, x, y, ICON, accent))
        brow = eyebrow(b, names)
        if brow:
            out.append(f'<text x="{x + ICON + 8:.1f}" y="{y + 13:.1f}" font-size="{EYEBROW}" '
                       f'font-weight="700" letter-spacing="1.2" fill="{accent}">'
                       f'{escape(brow)}</text>')
        y += ICON + 8
    if stereotype(b):
        out.append(f'<text x="{x:.1f}" y="{y + 12:.1f}" font-size="{SUB}" fill="{accent}">'
                   f'{escape(stereotype(b))}</text>')
        y += PITCH
    italic = ' font-style="italic"' if b.get("abstract") else ""
    out.append(f'<text x="{x:.1f}" y="{y + 14:.1f}" font-size="{TITLE}" font-weight="700"'
               f'{italic} fill="{t["text"]}">{escape(b["name"])}</text>')
    return out, y + 18 + PAD_Y


def divider(bx, y, accent):
    return (f'<line x1="{bx["l"]:.1f}" y1="{y:.1f}" x2="{bx["r"]:.1f}" y2="{y:.1f}" '
            f'stroke="{accent}" stroke-width="1" stroke-opacity="0.6"/>')


def draw_box(spec, b, bx, t, names):
    accent, tint = t["kinds"][b.get("kind", "neutral")]
    l, top, r, bot = bx["l"], bx["t"], bx["r"], bx["b"]
    out = [f'<g class="{spec["type"]}-box" data-box="{escape(b["id"])}">',
           (f'<rect x="{l:.1f}" y="{top:.1f}" width="{r - l:.1f}" height="{bot - top:.1f}" '
            f'rx="4" fill="{tint}" stroke="{accent}" stroke-width="1.3"/>')]
    head, y = draw_head(spec, b, bx, t, names, accent)
    out += head
    x = l + PAD_X
    if spec["type"] == "class":
        for lines in compartments(b):
            out.append(divider(bx, y, accent))
            for j, line in enumerate(lines):
                out.append(f'<text x="{x:.1f}" y="{y + 8 + 11 + PITCH * j:.1f}" '
                           f'font-size="{SUB}" fill="{t["text"]}">{escape(line)}</text>')
            y += 8 + PITCH * len(lines) + 6
    else:
        out.append(divider(bx, y, accent))
        y += 6
        room = tag_room(b)
        for col in b["columns"]:
            for k, tag in enumerate(tags(col)):
                tx = x + k * (TAG_W + 4)
                out.append(f'<rect class="tag" x="{tx:.1f}" y="{y + 3:.1f}" width="{TAG_W}" '
                           f'height="{TAG_H}" rx="2" fill="none" stroke="{accent}" '
                           f'stroke-width="1"/>')
                out.append(f'<text x="{tx + (TAG_W - text_width(tag, TAG, 0.5)) / 2:.1f}" '
                           f'y="{y + 13.2:.1f}" font-size="{TAG}" font-weight="700" '
                           f'letter-spacing="0.5" fill="{accent}">{tag}</text>')
            out.append(f'<text x="{x + room:.1f}" y="{y + 14:.1f}" font-size="{SUB}" '
                       f'fill="{t["text"]}">{escape(col["name"])}</text>')
            kind = col.get("type", "")
            if kind:
                out.append(f'<text x="{r - PAD_X - text_width(kind, SUB):.1f}" '
                           f'y="{y + 14:.1f}" font-size="{SUB}" fill="{t["sub"]}">'
                           f'{escape(kind)}</text>')
            y += ROW
    return [*out, "</g>"]


def end_place(pts, which, words):
    """Where the words by one end go: beside the line, close to the box. Returns
    (x, y) of the words' start and baseline."""
    (px, py), (qx, qy) = (pts[0], pts[1]) if which == "from" else (pts[-1], pts[-2])
    w = text_width(words, LABEL)
    if py == qy:   # a level end: the words above the line
        x = px - END_GAP - w if qx < px else px + END_GAP
        return x, py - 11
    x = px + 11    # an upright end: the words to the right of the line
    return x, (py + 15 if qy > py else py - 7)


# Checks.

def whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_text_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def check_types(spec):
    """Every part of the spec has the type the drawing needs, or a plain message
    says which one does not. The error is a ValueError, as for any other bad spec."""
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")  # noqa: TRY004
    for key in ("title", "desc"):
        if not isinstance(spec.get(key, ""), str):
            raise ValueError(f"the diagram's '{key}' must be text")  # noqa: TRY004
    names = spec.get("names", {})
    if not isinstance(names, dict) or not all(isinstance(v, str) for v in names.values()):
        raise ValueError("'names' must be an object of kind: label, such as "
                         '{"server": "Your machine"}')
    what = "classes" if spec["type"] == "class" else "tables"
    items = spec.get(what, [])
    if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
        raise ValueError(f"'{what}' must be a list of objects")
    for b in items:
        bid = b.get("id")
        if not isinstance(bid, str):
            raise ValueError(f"every box in '{what}' needs an 'id' that is text")  # noqa: TRY004
        if not whole(b.get("col")) or not whole(b.get("row")):
            raise ValueError(f"'{bid}' needs a whole number for 'col' and 'row'")
        for key in ("name", "kind", "icon", "stereotype"):
            if key in b and not isinstance(b[key], str):
                raise ValueError(f"'{bid}': '{key}' must be text")
        if "abstract" in b and not isinstance(b["abstract"], bool):
            raise ValueError(f"'{bid}': 'abstract' must be true or false")
        for key in ("fields", "methods"):
            if key in b and not is_text_list(b[key]):
                raise ValueError(f"'{bid}': '{key}' must be a list of text, one line each")
        if spec["type"] == "er":
            cols = b.get("columns", [])
            if not isinstance(cols, list) or not all(isinstance(c, dict) for c in cols):
                raise ValueError(f"table '{bid}': 'columns' must be a list of objects")
            for c in cols:
                for key in ("name", "type", "key"):
                    if key in c and not isinstance(c[key], str):
                        raise ValueError(f"table '{bid}': a column's '{key}' must be text")
    rels = spec.get("relations", [])
    if not isinstance(rels, list) or not all(isinstance(x, dict) for x in rels):
        raise ValueError("'relations' must be a list of objects")
    for rel in rels:
        for key in ("from", "to", "type", "label", "loop", "route"):
            if key in rel and not isinstance(rel[key], str):
                raise ValueError(f"a relation's '{key}' must be text")
        for key in ("ends", "roles"):
            if key in rel and not (is_text_list(rel[key]) and len(rel[key]) == 2):
                raise ValueError(f"a relation's '{key}' must be a pair of text: [from, to]")
        if "arrow" in rel and not isinstance(rel["arrow"], bool):
            raise ValueError("a relation's 'arrow' must be true or false")
        shift = rel.get("shift", 0)
        if not (state.number(shift) or (isinstance(shift, list) and len(shift) == 2
                                        and all(state.number(v) for v in shift))):
            raise ValueError("a relation's shift is a number, or a pair [from, to]")


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    check_types(spec)
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    noun = "class" if spec["type"] == "class" else "table"
    what = "classes" if noun == "class" else "tables"
    items = spec.get(what)
    if not items:
        raise ValueError(f"the diagram has no {what}")
    seen, cells = set(), {}
    kinds = set(THEMES["light"]["kinds"])
    for b in items:
        bid = b["id"]
        if not bid:
            raise ValueError(f"every {noun} needs an 'id'")
        if bid in seen:
            raise ValueError(f"two {what} share the id '{bid}'")
        seen.add(bid)
        if not b.get("name"):
            raise ValueError(f"{noun} '{bid}' needs a 'name'")
        if b.get("kind", "neutral") not in kinds:
            raise ValueError(f"{noun} '{bid}': kind must be one of {', '.join(sorted(kinds))}")
        if b.get("icon") and b["icon"] not in ICONS:
            raise ValueError(f"{noun} '{bid}': no icon named '{b['icon']}'")
        where = (b["col"], b["row"])
        if where in cells:
            raise ValueError(f"'{cells[where]}' and '{bid}' share col {b['col']}, row {b['row']}")
        cells[where] = bid
        if noun == "table":
            if not b.get("columns"):
                raise ValueError(f"table '{bid}' needs 'columns'")
            for c in b["columns"]:
                if not c.get("name"):
                    raise ValueError(f"table '{bid}': every column needs a 'name'")
                if c.get("key") not in (None, "", "pk", "fk", "pk fk"):
                    raise ValueError(f"table '{bid}', column '{c['name']}': key must be "
                                     "'pk', 'fk', or 'pk fk'")
    for rel in spec.get("relations", []):
        for end in ("from", "to"):
            if rel.get(end) not in seen:
                raise ValueError(f"a relation {end} '{rel.get(end)}', which is not a {noun}")
        if rel.get("loop") not in (None, *state.SIDES):
            raise ValueError(f"a relation's loop must be one of {', '.join(state.SIDES)}")
        if rel.get("route") not in (None, *state.ROUTES):
            raise ValueError(f"a relation's route must be one of {', '.join(state.ROUTES)}")
        if noun == "class":
            if rel.get("type", "association") not in RELATIONS:
                raise ValueError(f"no relation '{rel['type']}'; use one of "
                                 f"{', '.join(RELATIONS)}")
            if rel.get("type") in PARENTS and rel["from"] == rel["to"]:
                raise ValueError(f"class '{rel['from']}' {rel['type']} itself")
        else:
            ends = rel.get("ends")
            known = (*CROWS_FEET, *SHORT)
            if not ends or any(e not in known for e in ends):
                raise ValueError(f"an ER relation {rel['from']} -> {rel['to']} needs 'ends', a "
                                 f"pair of: {', '.join(known)}")
    if noun == "class":
        check_parents(spec.get("relations", []))


PARENTS = ("inherits", "implements")


def check_parents(rels):
    """No class is its own parent, through any chain of inherits and implements."""
    up = {}
    for rel in rels:
        if rel.get("type") in PARENTS:
            up.setdefault(rel["from"], []).append(rel["to"])
    done = set()
    for start in up:
        path, stack = [], [(start, iter(up.get(start, [])))]
        path.append(start)
        while stack:
            node, kids = stack[-1]
            kid = next(kids, None)
            if kid is None:
                done.add(node)
                stack.pop()
                path.pop()
            elif kid in path:
                ring = [*path[path.index(kid):], kid]
                raise ValueError("inherits and implements go in a circle: "
                                 + " -> ".join(ring))
            elif kid not in done:
                path.append(kid)
                stack.append((kid, iter(up.get(kid, []))))


def draw(spec, theme):
    if isinstance(spec, dict) and spec.get("type") not in ("class", "er"):
        raise ValueError("diagram.model draws a 'class' or an 'er' diagram")
    check(spec)
    t = THEMES[theme]
    names = {k: v.upper() for k, v in (spec.get("names") or {}).items()}
    boxes = layout(spec, names)
    rels = spec.get("relations", [])
    fake = {"states": [{"id": k} for k in boxes], "transitions": [rel_of(r) for r in rels]}
    lanes = state.loop_lanes(fake, boxes, range(len(rels)))
    seen = []
    for bx in boxes.values():
        seen += [(bx["l"], bx["t"]), (bx["r"], bx["b"])]

    lines, words = [], []
    for i, rel in enumerate(rels):
        pts, mid = route(rel, fake["transitions"][i], boxes, lanes.get(i))
        seen += pts
        dashed, start, end = line_style(spec, rel)
        attrs = (' stroke-dasharray="6 4"' if dashed else "")
        attrs += f' marker-start="url(#{marker_id(start)})"' if start else ""
        attrs += f' marker-end="url(#{marker_id(end)})"' if end else ""
        lines.append(f'<path class="relation" data-from="{escape(rel["from"])}" '
                     f'data-to="{escape(rel["to"])}" d="{rounded(pts)}" fill="none" '
                     f'stroke="{t["edge"]}" stroke-width="1.5" stroke-linejoin="round"{attrs}/>')
        for which, text in zip(("from", "to"), end_words(spec, rel), strict=True):
            if not text:
                continue
            x, y = end_place(pts, which, text)
            seen += [(x, y - LABEL * 0.8), (x + text_width(text, LABEL), y + LABEL * 0.25)]
            words.append(f'<text class="end" x="{x:.1f}" y="{y:.1f}" font-size="{LABEL}" '
                         f'fill="{t["sub"]}">{escape(text)}</text>')
        label = rel.get("label")
        if label:
            w, h = state.label_size(label)
            seen += [(mid[0] - w / 2, mid[1] - h / 2), (mid[0] + w / 2, mid[1] + h / 2)]
            words.append(f'<rect class="label" x="{mid[0] - w / 2:.1f}" y="{mid[1] - h / 2:.1f}" '
                         f'width="{w:.1f}" height="{h}" rx="3" fill="{t["page"]}" '
                         f'stroke="{t["border"]}" stroke-width="1"/>')
            words.append(f'<text x="{mid[0]:.1f}" y="{mid[1] + 3.8:.1f}" text-anchor="middle" '
                         f'font-size="{LABEL}" fill="{t["sub"]}">{escape(label)}</text>')
    body = [part for b in boxes_of(spec) for part in draw_box(spec, b, boxes[b["id"]], t, names)]

    x0 = min(p[0] for p in seen) - MARGIN
    y0 = min(p[1] for p in seen) - MARGIN
    x1 = max(p[0] for p in seen) + MARGIN
    y1 = max(p[1] for p in seen) + MARGIN
    w, h = x1 - x0, y1 - y0
    grid_ = (f'<pattern id="grid" x="{x0:.0f}" y="{y0:.0f}" width="24" height="24" '
             f'patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" '
             f'stroke="{t["grid"]}" stroke-width="1"/></pattern>')
    head = [
        (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.0f} {y0:.0f} {w:.0f} {h:.0f}" '
         f'width="{w:.0f}" height="{h:.0f}" role="img" aria-labelledby="title desc" '
         f'font-family="{MONO}">'),
        f'<title id="title">{escape(spec["title"])}</title>',
        f'<desc id="desc">{escape(spec["desc"])}</desc>',
        f'<defs>{"".join(markers(t))}{grid_}</defs>',
        # A full square: no corner is see-through, whatever the page behind it.
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="{t["page"]}"/>',
        f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{w:.0f}" height="{h:.0f}" fill="url(#grid)"/>',
    ]
    return "\n".join(head + lines + body + words + ["</svg>"]) + "\n"
