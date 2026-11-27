"""A C4 diagram with "style": "isometric": the same spec, drawn as a scene,
with the layout worked out from the grid. Tested through diagram.draw."""

import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET
from itertools import pairwise

from diagram import draw
from diagram.flow import THEMES, text_width
from tests.test_diagram_c4 import CONTAINER, CONTEXT, DEPLOYMENT, DYNAMIC, SRC

NS = "{http://www.w3.org/2000/svg}"
LEVELS = {"context": CONTEXT, "container": CONTAINER, "component": dict(CONTAINER,
                                                                         level="component"),
          "dynamic": DYNAMIC, "deployment": DEPLOYMENT}
EXAMPLES = ("c4-context", "c4-container", "c4-dynamic", "c4-deployment")
# A busier made-up spec: a grid of three by three, lanes across it, and two boundaries.
BUSY = {
    "type": "c4", "level": "component", "title": "A library",
    "desc": "Readers borrow books through an app; staff run the catalog.",
    "boundaries": [{"id": "lib", "name": "The library", "type": "Software System"},
                   {"id": "back", "name": "Back office", "type": "Software System",
                    "parent": "lib"}],
    "elements": [
        {"id": "reader", "type": "person", "name": "Reader",
         "description": "Borrows and returns books", "col": 0, "row": 0},
        {"id": "app", "type": "container", "name": "Library app", "tech": "Python",
         "description": "Lends books and takes returns", "col": 1, "row": 0, "parent": "lib"},
        {"id": "search", "type": "component", "name": "Search", "tech": "Python",
         "description": "Finds a book by its title", "col": 2, "row": 0, "parent": "lib"},
        {"id": "loans", "type": "database", "name": "Loans", "tech": "SQLite",
         "description": "Who has which book", "col": 1, "row": 1, "parent": "back"},
        {"id": "late", "type": "queue", "name": "Late notices", "tech": "Files",
         "description": "Letters to send", "col": 2, "row": 1, "parent": "back"},
        {"id": "staff", "type": "person", "name": "Staff", "kind": "check",
         "description": "Keeps the catalog", "col": 0, "row": 2},
        {"id": "mail", "type": "system", "external": True, "name": "Post office",
         "description": "Sends the letters", "col": 2, "row": 2},
    ],
    "relations": [
        {"from": "reader", "to": "app", "label": "Borrows a book", "tech": "HTTPS"},
        {"from": "app", "to": "search", "label": "Looks up"},
        {"from": "app", "to": "loans", "label": "Records the loan", "tech": "SQL"},
        {"from": "loans", "to": "late", "label": "Lists late books"},
        {"from": "late", "to": "mail", "label": "Sends a letter"},
        {"from": "staff", "to": "loans", "label": "Checks the loans"},
    ],
}


def iso(spec, **change):
    out = copy.deepcopy(spec)
    out.update(change, style="isometric")
    return out


def texts(svg):
    return [e.text or "" for e in ET.fromstring(svg).iter(f"{NS}text")]


class IsometricC4Test(unittest.TestCase):
    def test_every_level_draws_as_a_scene_in_light_and_dark(self):
        for level, spec in LEVELS.items():
            for theme in ("light", "dark"):
                with self.subTest(level=level, theme=theme):
                    svg = draw(iso(spec), theme)
                    root = ET.fromstring(svg)
                    self.assertEqual(root.get("role"), "img")
                    self.assertTrue(root.findall(f".//{NS}polyline"), "lanes, not flat arrows")
                    self.assertIn(THEMES[theme]["page"], svg)
                    found = texts(svg)
                    for e in spec["elements"]:
                        self.assertIn(e["name"].upper(), found)
                    for r in spec["relations"]:
                        self.assertTrue(any(r["label"] in t for t in found), r["label"])

    def test_nesting_three_deep_stacks_each_platform_on_the_one_below(self):
        def rise(levels):
            """How far the nested element stands above one on the ground beside it."""
            bounds = [{"id": f"b{k}", "name": f"Level {k}", "type": "node", "kind": "neutral",
                       **({"parent": f"b{k - 1}"} if k else {})} for k in range(levels)]
            spec = {"type": "c4", "level": "deployment", "title": "t", "desc": "d",
                    "style": "isometric", "boundaries": bounds,
                    "elements": [{"id": "in", "type": "container", "name": "Inside",
                                  "kind": "advisor", "col": 0, "row": 0,
                                  **({"parent": f"b{levels - 1}"} if levels else {})},
                                 {"id": "out", "type": "container", "name": "Outside",
                                  "kind": "ai", "col": 1, "row": 0}]}
            svg = draw(spec, "light")
            kinds = THEMES["light"]["kinds"]

            def bottom(kind):
                return max(float(v) for p in ET.fromstring(svg).iter(f"{NS}polygon")
                           if p.get("stroke") == kinds[kind][0]
                           for v in p.get("points").replace(",", " ").split()[1::2])
            return bottom("ai") - bottom("advisor")
        heights = [rise(n) for n in range(4)]
        self.assertEqual(heights, sorted(heights))
        self.assertEqual(len(set(heights)), 4, "each level of nesting lifts it higher")

    def test_no_words_overlap_and_nothing_is_clipped(self):
        found = list(LEVELS.items())
        found += [(n, json.loads((SRC / f"{n}.json").read_text())) for n in EXAMPLES]
        for name, spec in found:
            for theme in ("light", "dark"):
                with self.subTest(diagram=name, theme=theme):
                    assert_clean(self, draw(iso(spec), theme))

    def test_a_dynamic_diagram_sends_one_dot_through_the_steps_in_order(self):
        for spec in (DYNAMIC, json.loads((SRC / "c4-dynamic.json").read_text())):
            svg = draw(iso(spec), "light")
            root = ET.fromstring(svg)
            # The small dots of "packets" are not the ticket: the ticket is the one dot
            # that tells the order of the steps.
            groups = [g for g in root.iter(f"{NS}g") if g.get("class") == "ticket"]
            self.assertEqual(len(groups), 1, "one ticket")
            group = groups[0]
            motions = group.findall(f".//{NS}animateMotion")
            self.assertEqual(len(motions), 1, "one dot")
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", motions[0].get("path"))]
            dx, dy = numbers(group.get("transform") or "0 0")
            path = [(x + dx, y + dy) for x, y in zip(nums[::2], nums[1::2], strict=True)]
            # Each numbered label sits on its step's lane: the dot passes it, in order.
            passes = []
            for n in range(1, len(spec["relations"]) + 1):
                label = next(e for e in root.iter(f"{NS}text")
                             if (e.text or "").startswith(f"{n}. "))
                x, y = float(label.get("x")), float(label.get("y"))
                near = min(range(len(path) - 1), key=lambda i: gap(path[i], path[i + 1],
                                                                   (x, y)))
                self.assertLess(gap(path[near], path[near + 1], (x, y)), 40, n)
                passes.append(near)
            self.assertEqual(passes, sorted(passes))
            self.assertEqual(len(set(passes)), len(passes))

    def all_specs(self):
        found = list(LEVELS.items()) + [("busy", BUSY)]
        return found + [(n, json.loads((SRC / f"{n}.json").read_text())) for n in EXAMPLES]

    def test_no_platform_edge_and_no_lane_crosses_a_label(self):
        for name, spec in self.all_specs():
            with self.subTest(diagram=name):
                root = ET.fromstring(draw(iso(spec), "light"))
                lines = edges(root)
                for box, text, own in labels(root):
                    for a, b, lane in lines:
                        if own is None or lane != own:   # a lane runs under its own label
                            self.assertFalse(cuts(a, b, box), f"a line crosses '{text}'")

    def test_every_label_sits_next_to_its_part(self):
        for name, spec in self.all_specs():
            with self.subTest(diagram=name):
                root = ET.fromstring(draw(iso(spec), "light"))
                heads = {t: box for box, t, _ in labels(root)}
                for e in spec["elements"]:
                    part = next(g for g in root.iter(f"{NS}g")
                                if g.get("class") == "part" and g.get("data-name") == e["name"])
                    near = distance(heads[e["name"].upper()], extent(part))
                    self.assertLess(near, 30, f"{e['name']} is {near:.0f} from its label")

    def test_the_dot_rests_at_the_first_step_when_it_does_not_move(self):
        svg = draw(iso(json.loads((SRC / "c4-dynamic.json").read_text())), "light")
        root = ET.fromstring(svg)
        ticket = next(g for g in root.iter(f"{NS}g") if g.get("class") == "ticket")
        # Where a reader sees it with no animation: its circles, moved by its transform.
        dx, dy = (float(v) for v in re.findall(r"-?\d+(?:\.\d+)?",
                                              ticket.get("transform") or "0 0"))
        circle = ticket.find(f"{NS}circle")
        still = (float(circle.get("cx") or 0) + dx, float(circle.get("cy") or 0) + dy)
        motion = ticket.find(f"{NS}animateMotion")
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", motion.get("path"))]
        start = (nums[0] + dx, nums[1] + dy)
        self.assertLess(abs(still[0] - start[0]) + abs(still[1] - start[1]), 1)
        self.assertGreater(still[0] + still[1], 100, "not at the corner of the page")
        one = next(e for e in root.iter(f"{NS}text") if (e.text or "").startswith("1. "))
        self.assertLess(abs(float(one.get("x")) - still[0]) + abs(float(one.get("y"))
                                                                  - still[1]), 260)

    def test_a_loop_is_refused_in_isometric_with_a_plain_error(self):
        looped = copy.deepcopy(CONTAINER)
        looped["relations"].append({"from": "web", "to": "web", "label": "Retries",
                                    "loop": "right"})
        draw(looped, "light")   # flat draws it
        with self.assertRaises(ValueError) as err:
            draw(iso(looped), "light")
        self.assertIn("loop", str(err.exception))

    def test_an_unknown_style_gives_a_plain_error(self):
        for bad in ("3d", 5):
            with self.subTest(style=bad), self.assertRaises(ValueError) as err:
                draw(dict(CONTEXT, style=bad), "light")
            self.assertIn("style", str(err.exception))


def numbers(text):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", text)]


def labels(root):
    """The page box of each label's words, outside the frames of lane labels, and of
    each lane label's frame."""
    out = []
    for e in root.iter(f"{NS}text"):
        if e.get("font-size") != "12":
            continue
        width = text_width(e.text or "", 12, float(e.get("letter-spacing") or 0))
        x, y = float(e.get("x")), float(e.get("y"))
        anchor = e.get("text-anchor")
        left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        out.append(((left, y - 10, left + width, y + 3), e.text, None))
    for r in root.iter(f"{NS}rect"):
        if r.get("class") == "pill":
            x, y = float(r.get("x")), float(r.get("y"))
            out.append(((x, y, x + float(r.get("width")), y + float(r.get("height"))),
                        "a lane's label", r.get("data-lane")))
    return out


def edges(root):
    """Every line a reader sees on the page: the edges of each zone, and each lane,
    with the number of the lane."""
    out = []
    for e in root.iter():
        if e.get("class") == "zone" or e.get("class") in ("main", "side"):
            n = numbers(e.get("points"))
            pts = list(zip(n[::2], n[1::2], strict=True))
            if e.get("class") == "zone":
                pts.append(pts[0])
            out += [(a, b, e.get("data-lane")) for a, b in pairwise(pts)]
    return out


def cuts(a, b, box):
    """True when the segment a-b passes through the box."""
    for k in range(41):
        x, y = a[0] + (b[0] - a[0]) * k / 40, a[1] + (b[1] - a[1]) * k / 40
        if box[0] < x < box[2] and box[1] < y < box[3]:
            return True
    return False


def extent(group):
    """The page box of what a group draws."""
    xs, ys = [], []
    for e in group.iter():
        tag = e.tag.removeprefix(NS)
        if tag in ("polygon", "polyline"):
            n = numbers(e.get("points"))
            xs += n[::2]
            ys += n[1::2]
        elif tag in ("ellipse", "circle"):
            cx, cy = float(e.get("cx")), float(e.get("cy"))
            rx = float(e.get("rx") or e.get("r"))
            ry = float(e.get("ry") or e.get("r"))
            xs += [cx - rx, cx + rx]
            ys += [cy - ry, cy + ry]
        elif tag == "path":
            for x, y in path_points(e.get("d")):
                xs.append(x)
                ys.append(y)
        elif tag == "rect":
            x, y = float(e.get("x")), float(e.get("y"))
            xs += [x, x + float(e.get("width"))]
            ys += [y, y + float(e.get("height"))]
    return min(xs), min(ys), max(xs), max(ys)


def path_points(d):
    """The points a path passes through, with the bottom of each arc."""
    out, x, y = [], 0.0, 0.0
    for cmd, args in re.findall(r"([MLVHAQZ])([^MLVHAQZ]*)", d):
        n = numbers(args)
        if cmd in "ML":
            x, y = n[0], n[1]
        elif cmd == "V":
            y = n[0]
        elif cmd == "H":
            x = n[0]
        elif cmd == "Q":
            out.append((n[0], n[1]))
            x, y = n[2], n[3]
        elif cmd == "A":
            out.append(((x + n[5]) / 2, max(y, n[6]) + n[1]))   # the arc bulges down
            x, y = n[5], n[6]
        out.append((x, y))
    return out


def distance(a, b):
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def gap(a, b, p):
    """The distance from page point p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / max(dx * dx + dy * dy,
                                                                        1e-9)))
    return ((a[0] + t * dx - p[0]) ** 2 + (a[1] + t * dy - p[1]) ** 2) ** 0.5


def assert_clean(test, svg):
    """No two words overlap, and no word, lane, or shape leaves the picture."""
    root = ET.fromstring(svg)
    x0, y0, w, h = (float(v) for v in root.get("viewBox").split())
    boxes = []
    for e in root.iter(f"{NS}text"):
        size = float(e.get("font-size"))
        width = text_width(e.text or "", size, float(e.get("letter-spacing") or 0))
        x, y = float(e.get("x")), float(e.get("y"))
        anchor = e.get("text-anchor")
        left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
        boxes.append((left, y - size * 0.8, left + width, y + size * 0.25, e.text))
    for a, (l, t, r, b, text) in enumerate(boxes):
        test.assertTrue(x0 <= l and r <= x0 + w and y0 <= t and b <= y0 + h, f"clipped: {text}")
        for l2, t2, r2, b2, other in boxes[a + 1:]:
            test.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, (text, other))
    for e in list(root.iter(f"{NS}polyline")) + list(root.iter(f"{NS}polygon")):
        nums = [float(v) for v in e.get("points").replace(",", " ").split()]
        for x, y in zip(nums[::2], nums[1::2], strict=True):
            test.assertTrue(x0 <= x <= x0 + w and y0 <= y <= y0 + h, "a shape is cut off")


if __name__ == "__main__":
    unittest.main()
