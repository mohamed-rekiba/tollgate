"""A C4 diagram drawn as an isometric scene: "style": "isometric" on a c4 spec.

The spec is the same as for the flat drawing (see diagram/c4.py). This module
works out the scene from it: where each object stands, how high each platform
is, which way each lane runs, and where each label goes, so that no two words
touch. Then diagram/scene.py draws it.

- The grid: "col" runs along x (down and to the right on the page) and "row"
  along y (down and to the left), so the author's layout is kept, turned on
  its corner.
- A boundary is a raised zone in its kind's color, sized to hold what it
  holds. A boundary inside another stands on it, one level higher, so nested
  deployment nodes stack.
- Each element type has its own object: a person, a building for a system,
  gray for an external one, a box with a lid for a container, a cylinder for a
  database, a pipe for a queue, a small block for a component, a cloud for a
  node whose stereotype says cloud, and a server for any other node.
- Each relation is a lane with dots that move, and its label: what happens,
  then how in brackets. At the dynamic level one dot follows the steps in the
  order they are listed, and the labels carry their numbers.
"""

import textwrap
from itertools import pairwise

from diagram import c4, scene
from diagram.flow import text_width

PITCHES = tuple(range(330, 760, 25))   # ground units from one cell to the next, to try
SCALE = 0.6
STEP = 16          # from one line of a label to the next
PLATE = 18         # the height of one platform
PAD = 100          # from an element's center to the edge of its zone
NEST = 34          # from a zone to the edge of the zone that holds it
MARGIN = 40
NEAR = 26          # the farthest a name may sit from its part, in pixels
SLACK = 200        # page area a label may cover of an object's box, in square pixels
TOP = 120          # room for the caption
WRAP = 24
PILL_WRAP = 24     # characters on a line of a lane's label

# Each element type: the scene object, half its footprint along x and y, its height.
SHAPES = {"person": ("person", 22, 22, 111), "system": ("building", 49, 49, 105),
          "container": ("container", 45, 45, 62), "database": ("database", 25, 25, 60),
          "queue": ("queue", 20, 48, 44), "component": ("component", 28, 28, 39),
          "cloud": ("cloud", 38, 38, 108), "node": ("server", 45, 45, 52)}
SUBS = {"context": "who uses it, and the systems around it",
        "container": "the parts inside it, and what flows between them",
        "component": "the parts of one container, and what flows between them",
        "dynamic": "one run, step by step, in order",
        "deployment": "where each part runs"}


def page(x, y, z=0.0):
    """A ground point on the page, with the origin at (0, 0)."""
    return (x - y) * 0.866 * SCALE, ((x + y) * 0.5 - z) * SCALE


def ground(px, py):
    """The point on the ground, z = 0, that falls on a page point."""
    a, b = px / (0.866 * SCALE), 2 * py / SCALE
    return (a + b) / 2, (b - a) / 2


def balanced(text, width):
    """Wrap text in as few lines as `width` allows, of near equal length: no word alone."""
    lines = textwrap.wrap(text, width)
    if not lines:
        return []
    for w in range(max(len(text) // len(lines), 1), width + 1):
        even = textwrap.wrap(text, w)
        if len(even) == len(lines):
            return even
    return lines


def overlap(a, b, gap=6):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def area(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def box_of(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def crosses_box(a, b, box, pad=2):
    """True when the page segment a-b passes through the box, grown by pad: an exact
    clip of the segment to the box."""
    lo, hi = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - box[0] + pad), (dx, box[2] + pad - a[0]),
                 (-dy, a[1] - box[1] + pad), (dy, box[3] + pad - a[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            lo = max(lo, t)
        else:
            hi = min(hi, t)
        if lo > hi:
            return False
    return True


class Layout:
    def __init__(self, spec, pitch):
        self.spec = spec
        self.pitch = pitch
        self.misses = 0.0   # how much the labels cover what they should not
        self.level = spec["level"]
        self.bounds = {b["id"]: b for b in spec.get("boundaries", [])}
        self.items = {e["id"]: self.item(e) for e in spec["elements"]}
        self.spots = {}   # the page box of each element's label, once placed
        self.first = {}   # where each element's label went the first time
        self.zones = []
        self.blocked = [i["box"] for i in self.items.values()]
        self.lanes = [self.route(n, r) for n, r in enumerate(spec.get("relations", []))]
        self.labels = []
        self.words = []   # the page box of every label placed so far

    # Where things stand ---------------------------------------------------------
    def depth(self, bid):
        n = 0
        while bid:
            n, bid = n + 1, self.bounds[bid].get("parent")
        return n

    def item(self, e):
        kind = "neutral" if e.get("external") else (
            e.get("kind") or ("you" if e["type"] == "person" else "server"))
        shape = e["type"]
        if shape == "node" and "cloud" in (e.get("stereotype") or "").lower():
            shape = "cloud"
        obj, hx, hy, tall = SHAPES[shape]
        if shape == "system" and e.get("external"):
            obj = "external"
        x, y = e["col"] * self.pitch, e["row"] * self.pitch
        z = (self.depth(e.get("parent")) + (1 if self.focus(e) else 0)) * PLATE
        corners = [page(x + dx, y + dy, z + dz) for dx in (-hx, hx) for dy in (-hy, hy)
                   for dz in (0, tall)]
        if e.get("icon"):
            tall += 56
            corners.append(page(x, y, z + tall + 14))
        return {"e": e, "kind": kind, "object": obj, "x": x, "y": y, "z": z, "hx": hx,
                "hy": hy, "tall": tall, "box": box_of(corners)}

    def focus(self, e):
        """At the context level, the system the diagram is about stands on its own zone."""
        return (self.level == "context" and e["type"] == "system" and not e.get("external")
                and not e.get("parent"))

    def held_kind(self, bid):
        """A boundary with no kind takes the kind of what it holds, when all of it is
        one kind and none of it is outside; otherwise it is gray."""
        kinds = set()
        for i in self.items.values():
            at = i["e"].get("parent")
            while at and at != bid:
                at = self.bounds[at].get("parent")
            if at == bid:
                kinds.add(i["kind"])
        return kinds.pop() if len(kinds) == 1 else "neutral"

    @staticmethod
    def on_ground(box, z):
        """The ground rectangle, at height z, that holds a page box."""
        lift = z * SCALE
        corners = [ground(px, py + lift) for px in (box[0] - 10, box[2] + 10)
                   for py in (box[1] - 10, box[3] + 10)]
        return (min(c[0] for c in corners), min(c[1] for c in corners),
                max(c[0] for c in corners), max(c[1] for c in corners))

    def room(self, eid):
        """The ground an element needs on its zone: its own, and its label's."""
        i = self.items[eid]
        parts = [(i["x"] - PAD, i["y"] - PAD, i["x"] + PAD, i["y"] + PAD)]
        if eid in self.spots:
            parts.append(self.on_ground(self.spots[eid], i["z"]))   # on the zone's top
        return (min(p[0] for p in parts), min(p[1] for p in parts),
                max(p[2] for p in parts), max(p[3] for p in parts))

    def chain(self, eid):
        """The boundaries an element is in, the innermost first."""
        out, at = [], self.items[eid]["e"].get("parent")
        while at:
            out.append(at)
            at = self.bounds[at].get("parent")
        return out

    def lane_room(self, bid):
        """The ground the labels of lanes inside a boundary need on it."""
        out = []
        for lane in self.lanes:
            if "box" not in lane:
                continue
            a, b = self.chain(lane["r"]["from"]), self.chain(lane["r"]["to"])
            shared = next((k for k in a if k in b), None)
            if shared == bid:
                out.append(self.on_ground(lane["box"], self.depth(bid) * PLATE))
        return out

    def place_zones(self):
        """Each boundary's rectangle on the ground, from what it holds and the labels of
        what it holds, inner ones first."""
        rects = {}

        def rect(bid):
            if bid in rects:
                return rects[bid]
            parts = [self.room(k) for k, i in self.items.items() if i["e"].get("parent") == bid]
            parts += self.lane_room(bid)
            parts += [(a - NEST, b - NEST, c + NEST, d + NEST) for a, b, c, d in
                      (rect(k) for k, b in self.bounds.items() if b.get("parent") == bid)]
            rects[bid] = (min(p[0] for p in parts), min(p[1] for p in parts),
                          max(p[2] for p in parts), max(p[3] for p in parts))
            return rects[bid]

        out = []
        for bid, b in self.bounds.items():
            d = self.depth(bid)
            out.append({"id": bid, "b": b, "at": rect(bid), "z": (d - 1) * PLATE, "depth": d,
                        "kind": b.get("kind") or self.held_kind(bid)})
        for k, i in self.items.items():
            if self.focus(i["e"]):
                out.append({"id": None, "b": {}, "at": self.room(k), "z": 0, "depth": 1,
                            "kind": i["kind"]})
        return sorted(out, key=lambda z: z["depth"])

    # Lanes ----------------------------------------------------------------------
    def taken(self, x, y, skip):
        return any(abs(i["x"] - x) < 1 and abs(i["y"] - y) < 1 for k, i in self.items.items()
                   if k not in skip)

    def route(self, n, r):
        a, b = self.items[r["from"]], self.items[r["to"]]
        skip = {r["from"], r["to"]}
        (xa, ya), (xb, yb) = (a["x"], a["y"]), (b["x"], b["y"])
        if ya == yb or xa == xb:
            along = "x" if ya == yb else "y"
            lo, hi = sorted((xa, xb) if along == "x" else (ya, yb))
            cells = range(int(lo + self.pitch), int(hi), self.pitch)
            if any(self.taken(c, ya, skip) if along == "x" else self.taken(xa, c, skip)
                   for c in cells):
                # Around what stands between: out to the street and back.
                off = self.pitch / 2
                if along == "x":
                    pts = [(xa, ya), (xa, ya + off), (xb, yb + off), (xb, yb)]
                else:
                    pts = [(xa, ya), (xa + off, ya), (xb + off, yb), (xb, yb)]
            else:
                pts = [(xa, ya), (xb, yb)]
        else:
            first_x = (xb, ya)   # along x first, then along y
            first_y = (xa, yb)
            want = r.get("route")
            if want == "vh":
                corner = first_y
            elif want in ("hv", "vhv"):
                corner = first_x
            else:
                corner = first_y if self.taken(*first_x, skip) else first_x
            pts = [(xa, ya), corner, (xb, yb)]
        pts = self.spread(pts)
        return {"r": r, "n": n + 1, "ground": self.trim(pts, a, b)}

    def spread(self, pts):
        """Move a lane sideways off a lane that already runs on the same line."""
        used = getattr(self, "used", [])
        out = list(pts)
        for i, (p, q) in enumerate(pairwise(pts)):
            along = 0 if abs(p[1] - q[1]) < 1 else 1   # 0: along x, 1: along y
            line = p[1] if along == 0 else p[0]
            lo, hi = sorted((p[along], q[along]))
            shift = 0
            while any(u[0] == along and abs(u[1] - (line + shift)) < 20 and u[2] < hi
                      and lo < u[3] for u in used):
                shift = -shift + 26 if shift <= 0 else -shift
            used.append((along, line + shift, lo, hi))
            if shift:
                for k in (i, i + 1):
                    x, y = out[k]
                    out[k] = (x, y + shift) if along == 0 else (x + shift, y)
        self.used = used
        return out

    @staticmethod
    def trim(pts, a, b):
        """Start and end the lane at the edge of each object, with its height."""
        pts = [list(p) for p in pts]
        for end, item, nxt in ((0, a, 1), (-1, b, -2)):
            p, q = pts[end], pts[nxt]
            dx, dy = q[0] - p[0], q[1] - p[1]
            far = max(abs(dx) + abs(dy), 1)
            cut = (item["hx"] if abs(dx) > abs(dy) else item["hy"]) + 16
            cut = min(cut, far / 2 - 1)
            pts[end] = [p[0] + dx / far * cut, p[1] + dy / far * cut]
        za, zb = a["z"] + 2, b["z"] + 2
        out = [(*pts[0], za)]
        for p in pts[1:-1]:
            out.append((*p, za))
        out.append((*pts[-1], zb))
        return out

    # Labels ---------------------------------------------------------------------
    def rows(self, head, subs, x, y, anchor):
        """The page box of each line of a label whose head sits at (x, y): a line may
        pass beside a short line of a label, where it would cut a long one."""
        out = []
        for k, (text, width) in enumerate([(head, text_width(head.upper(), 12, 1.4))] +
                                          [(t, text_width(t, 12)) for t in subs]):
            left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
            base = y + STEP * k
            out.append((left - 2, base - 11, left + width + 2, base + 4))
        return out

    def lines(self):
        """Every line on the page: the edges of each zone, and each lane with its number."""
        if not hasattr(self, "_lines"):
            out = []
            for z in self.zones:
                x0, y0, x1, y1 = z["at"]
                lo, hi = z["z"], z["z"] + PLATE
                a, b, c, d = (page(x0, y1, hi), page(x1, y1, hi), page(x1, y0, hi),
                              page(x0, y0, hi))
                a0, b0, c0 = page(x0, y1, lo), page(x1, y1, lo), page(x1, y0, lo)
                for p, q in ((a, b), (b, c), (c, d), (d, a), (a, a0), (b, b0), (c, c0),
                             (a0, b0), (b0, c0)):
                    out.append((p, q, None))
            for lane in self.lanes:
                pts = [page(*p) for p in lane["ground"]]
                out += [(p, q, lane["n"]) for p, q in pairwise(pts)]
            self._lines = out
        return self._lines

    def crossings(self, box, own=None):
        """How many lines cross the box, but for the lane it labels."""
        return sum(1 for p, q, n in self.lines() if (own is None or n != own)
                   and crosses_box(p, q, box))

    def covers(self, rows, own=None):
        """How much a label covers what it should not: objects, words, and lines."""
        # An object's box holds empty corners, so a small overlap is still clear.
        return sum(max(area(box, o) - SLACK, 0) for box in rows for o in self.blocked) + sum(
            sum(10000 + area(box, o) for o in self.words if overlap(box, o, 2))
            + 10000 * self.crossings(box, own) for box in rows)

    def free(self, rows, own=None):
        """The cost of a spot: words on words, or a line through words, cannot be read,
        so they cost far more than words on the edge of a picture."""
        return sum(sum(area(box, o) + 1 for o in self.blocked if overlap(box, o))
                   + sum(10000 + area(box, o) for o in self.words if overlap(box, o))
                   + 10000 * self.crossings(box, own) for box in rows)

    def place_label(self, head, subs, spots):
        """Put a label at the first spot where it touches nothing, or the least bad one.
        Return the page box of the whole label."""
        best = None
        for x, y, anchor in spots:
            rows = self.rows(head, subs, x, y, anchor)
            cost = self.free(rows)
            if best is None or cost < best[0]:
                best = (cost, x, y, anchor, rows)
            if cost == 0:
                break
        _, x, y, anchor, rows = best
        self.misses += self.covers(rows)
        self.words.extend(rows)
        self.labels.append({"head": head, "sub": subs, "page": (x, y), "anchor": anchor})
        return box_of([(r[0], r[1]) for r in rows] + [(r[2], r[3]) for r in rows])

    def label_elements(self):
        for i in self.items.values():
            e = i["e"]
            subs = [c4.type_line(e)]
            for part in (e.get("description") or "").split("\n"):
                subs += balanced(part, WRAP)
            l, t, r, b = i["box"]
            cx = (l + r) / 2
            h = STEP * len(subs)
            # Every spot keeps the name within NEAR of its part: beside it, under it,
            # or over it, sliding along that side.
            spots = [(cx + dx, b + 20, "middle") for dx in (0, -30, 30, -60, 60)]
            for y in range(int(t + 10), int(b + NEAR), 12):
                spots += [(r + 14, y, "start"), (l - 14, y, "end")]
            spots += [(cx + dx, t - 10 - h, "middle") for dx in (0, -30, 30)
                      if h <= NEAR]
            if e["id"] in self.first:
                spots.insert(0, self.first[e["id"]])   # the spot its zone grew to hold
            self.spots[e["id"]] = self.place_label(e["name"], subs, spots)
            self.first.setdefault(e["id"], self.labels[-1]["page"] + (self.labels[-1]["anchor"],))

    def label_zones(self):
        for z in self.zones:
            b = z["b"]
            if not b.get("name"):
                continue
            kind = b.get("type")
            if kind:
                kind = f"«{kind}»" if self.level == "deployment" else f"[{kind}]"
            subs = [kind] if kind else []
            x0, y0, x1, y1 = z["at"]
            top = z["z"] + PLATE
            h = STEP * len(subs)
            spots = []
            # On the zone, near its left corner, then along its back edges; then outside.
            for k in range(7):
                f = k / 6
                p = page(x0 + 24, y1 - 30 - (y1 - y0 - 60) * f, top)
                spots.append((p[0] + 6, p[1] - h - 4, "start"))
                q = page(x0 + 30 + (x1 - x0 - 60) * f, y0 + 24, top)
                spots.append((q[0], q[1] + 22, "middle"))
            left, back = page(x0, y1, top), page(x0, y0, top)
            right, front = page(x1, y0, top), page(x1, y1, top)
            for dy in (0, -20, 20, -40):
                spots += [(left[0] - 16, left[1] + dy, "end"), (right[0] + 16, right[1] + dy,
                                                                "start")]
            spots += [(back[0] + dx, back[1] - 14 - h, "middle") for dx in (0, -80, 80)]
            spots += [(front[0] + dx, front[1] + 40, "middle") for dx in (0, -80, 80)]
            self.place_label(b["name"], subs, spots)

    def place_pills(self):
        for lane in self.lanes:
            r = lane["r"]
            what = f"{lane['n']}. {r['label']}" if self.level == "dynamic" else r["label"]
            # Short lines: a narrow label fits beside a short lane.
            lines = balanced(what, PILL_WRAP)
            lines += [f"[{r['tech']}]"] if r.get("tech") else []
            text = "\n".join(lines)
            w = max(len(s) for s in lines) * 6.6 + 16
            h = 20 + scene.PILL_STEP * (len(lines) - 1)
            pts = [page(*p) for p in lane["ground"]]
            best = None
            tries = sorted((k / 50 for k in range(5, 46)), key=lambda t: abs(t - 0.5))
            if "at" in lane:
                tries.insert(0, lane["at"])   # where its zone grew to hold it
            for at in tries:
                px, py = scene.Scene.along(pts, at)
                box = (px - w / 2, py - h / 2, px + w / 2, py + h / 2)
                cost = self.free([box], own=lane["n"])
                if best is None or cost < best[0]:
                    best = (cost, at, box)
                if cost == 0:
                    break
            _, at, box = best
            self.misses += self.covers([box], own=lane["n"])
            self.words.append(box)
            lane.update(label=text, at=at, box=box)

    # The scene ------------------------------------------------------------------
    def scene(self):
        # First the labels with no zones; then each zone grows to hold its parts and
        # their labels, and the labels are placed again, now clear of every edge.
        self.label_elements()
        self.place_pills()
        self.zones = self.place_zones()
        self.words, self.labels, self.misses = [], [], 0.0
        del self._lines
        self.label_elements()
        self.label_zones()
        self.place_pills()
        prefix, _ = c4.LEVELS[self.level]
        title = f"{prefix} diagram for {self.spec['title']}"
        boxes = self.blocked + self.words
        for z in self.zones:
            x0, y0, x1, y1 = z["at"]
            boxes.append(box_of([page(x, y, zz) for x in (x0, x1) for y in (y0, y1)
                                 for zz in (z["z"], z["z"] + PLATE)]))
        for lane in self.lanes:
            boxes.append(box_of([page(*p) for p in lane["ground"]]))
        left, top, right, bottom = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                                    max(b[2] for b in boxes), max(b[3] for b in boxes))
        caption = [title, SUBS[self.level]]
        width = max(right - left + 2 * MARGIN, text_width(title.upper(), 13, 2) + 2 * MARGIN)
        ox, oy = MARGIN - left, TOP - top
        height = bottom - top + TOP + MARGIN
        span = max(abs(v) for i in self.items.values() for v in (i["x"], i["y"])) + self.pitch
        out = {"type": "scene", "title": title, "desc": self.spec["desc"],
               "size": [round(width), round(height)], "origin": [round(ox, 1), round(oy, 1)],
               "scale": SCALE, "grid": round(span + self.pitch), "caption": caption,
               "zones": [{"at": list(z["at"]), "kind": z["kind"],
                          "z": z["z"], "height": PLATE} for z in self.zones],
               "lanes": [], "objects": [], "labels": []}
        # A lane's "at" is a share of its length on the page, so the origin does not move it.
        for lane in self.lanes:
            r = lane["r"]
            entry = {"path": [list(p) for p in lane["ground"]], "label": lane["label"],
                     "at": lane["at"]}
            if r.get("tone"):
                entry["tone"] = r["tone"]
            if r.get("dashed"):
                entry["side"] = True
            out["lanes"].append(entry)
        for i in self.items.values():
            o = {"type": i["object"], "at": [i["x"], i["y"]], "z": i["z"],
                 "name": i["e"]["name"]}
            if i["object"] != "external":
                o["kind"] = i["kind"]
            out["objects"].append(o)
            if i["e"].get("icon"):
                out["badges"] = out.get("badges", []) + [
                    {"at": [i["x"], i["y"], i["z"] + i["tall"]], "icon": i["e"]["icon"],
                     "kind": i["kind"]}]
        for label in self.labels:
            gx, gy = ground(*label["page"])
            out["labels"].append({"at": [round(gx, 1), round(gy, 1), 0], "head": label["head"],
                                  "sub": label["sub"], "anchor": label["anchor"],
                                  "halo": True})
        if self.level == "dynamic" and self.lanes:
            out["ticket"] = {"legs": [{"path": [list(p) for p in lane["ground"]], "wait": 0.5}
                                      for lane in self.lanes]}
        return out


def to_scene(spec):
    """The C4 spec as a scene spec."""
    c4.check(spec)
    for r in spec.get("relations", []):
        if r.get("loop") or r["from"] == r["to"]:
            raise ValueError(f"the relation {r['from']} -> {r['to']} is a loop, and an "
                             "isometric drawing has no loops: draw it flat, or leave it out")
    # The tightest grid on which no label covers an object or another label.
    best = None
    for pitch in PITCHES:
        layout = Layout(spec, pitch)
        out = layout.scene()
        if best is None or layout.misses < best[0]:
            best = (layout.misses, out)
        if not layout.misses:
            break
    out = best[1]
    if spec.get("packets"):
        out["packets"] = True
    return out


def draw(spec, theme):
    return scene.from_spec(to_scene(spec), theme)
