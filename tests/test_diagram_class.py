"""The class diagram kind: classes in three compartments, the six UML relations
with their standard ends, multiplicity and roles at the ends, and a label."""

import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path

from diagram import draw
from diagram.flow import THEMES, text_width

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src" / "plan-model.json"

NS = "{http://www.w3.org/2000/svg}"


def words(svg):
    return " ".join(e.text or "" for e in ET.fromstring(svg).iter(f"{NS}text"))


def numbers(d):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]


def outline(svg, cid):
    """The outline of a class as (left, top, right, bottom)."""
    rect = ET.fromstring(svg).find(f".//{NS}g[@data-box='{cid}']/{NS}rect")
    x, y = float(rect.get("x")), float(rect.get("y"))
    return x, y, x + float(rect.get("width")), y + float(rect.get("height"))


def lines(svg):
    return [p for p in ET.fromstring(svg).iter(f"{NS}path") if p.get("class") == "relation"]


def ends_of(svg, a, b):
    """The relation drawn between two classes."""
    (found,) = [p for p in lines(svg) if p.get("data-from") == a and p.get("data-to") == b]
    return found


def marker(svg, url):
    mid = re.match(r"url\(#(.+)\)", url).group(1)
    return ET.fromstring(svg).find(f".//{NS}marker[@id='{mid}']")


SPEC = {
    "type": "class", "title": "Shapes", "desc": "Shapes on a canvas, drawn by a painter.",
    "names": {"server": "Storage"},
    "classes": [
        {"id": "shape", "name": "Shape", "abstract": True, "col": 1, "row": 0, "kind": "ai",
         "fields": ["name: str"], "methods": ["area() float"]},
        {"id": "drawable", "name": "Drawable", "stereotype": "interface", "col": 2, "row": 0,
         "kind": "check", "methods": ["draw(canvas)"]},
        {"id": "circle", "name": "Circle", "col": 1, "row": 1, "kind": "ai",
         "fields": ["radius: float"]},
        {"id": "canvas", "name": "Canvas", "col": 0, "row": 0, "kind": "you",
         "fields": ["width: int", "height: int"], "methods": ["clear()"]},
        {"id": "layer", "name": "Layer", "col": 0, "row": 1, "kind": "server", "icon": "folder",
         "fields": ["order: int"]},
        {"id": "painter", "name": "Painter", "col": 2, "row": 1, "kind": "advisor",
         "methods": ["paint(shape)"]},
    ],
    "relations": [
        {"from": "circle", "to": "shape", "type": "inherits"},
        {"from": "shape", "to": "drawable", "type": "implements"},
        {"from": "canvas", "to": "layer", "type": "owns", "ends": ["1", "1..*"],
         "roles": ["", "layers"]},
        {"from": "canvas", "to": "shape", "type": "has", "ends": ["1", "0..*"]},
        {"from": "painter", "to": "drawable", "type": "uses", "label": "calls"},
        {"from": "layer", "to": "circle", "type": "association", "arrow": True,
         "label": "shows"},
    ],
}


def spec(**change):
    out = copy.deepcopy(SPEC)
    out.update(change)
    return out


class ClassTest(unittest.TestCase):
    def test_every_class_draws_its_name_fields_and_methods(self):
        svg = draw(SPEC, "light")
        for text in ("Shape", "name: str", "area() float", "Circle", "radius: float",
                     "Canvas", "clear()", "Painter", "paint(shape)", "AI", "YOU", "STORAGE"):
            self.assertIn(text, words(svg))
        self.assertIn("«interface»", words(svg), "a stereotype in guillemets")
        root = ET.fromstring(svg)
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.find(f"{NS}title").text, "Shapes")

    def test_an_abstract_class_has_its_name_in_italics(self):
        root = ET.fromstring(draw(SPEC, "light"))
        italic = [e.text for e in root.iter(f"{NS}text") if e.get("font-style") == "italic"]
        self.assertEqual(italic, ["Shape"])

    def test_compartments_show_only_what_the_class_has(self):
        root = ET.fromstring(draw(SPEC, "light"))

        def dividers(cid):
            return len(root.findall(f".//{NS}g[@data-box='{cid}']/{NS}line"))

        self.assertEqual(dividers("shape"), 2, "name, fields, methods")
        self.assertEqual(dividers("circle"), 1, "name and fields")
        self.assertEqual(dividers("drawable"), 1, "name and methods")

    def test_each_relation_has_its_uml_line_and_end(self):
        svg = draw(SPEC, "light")
        page, edge = THEMES["light"]["page"], THEMES["light"]["edge"]
        cases = [  # from, to, dashed, end at "from", end at "to"
            ("circle", "shape", False, None, "triangle"),
            ("shape", "drawable", True, None, "triangle"),
            ("canvas", "layer", False, "diamond", None),
            ("canvas", "shape", False, "open diamond", None),
            ("painter", "drawable", True, None, "arrow"),
            ("layer", "circle", False, None, "arrow"),
        ]
        drawn = {}
        for a, b, dashed, start, end in cases:
            with self.subTest(relation=f"{a} -> {b}"):
                line = ends_of(svg, a, b)
                self.assertEqual(line.get("stroke-dasharray") is not None, dashed)
                for attr, name in (("marker-start", start), ("marker-end", end)):
                    if name is None:
                        self.assertIsNone(line.get(attr))
                    else:
                        drawn[name] = marker(svg, line.get(attr))
                        self.assertEqual(drawn[name].get("data-end"), name)
        hollow = drawn["triangle"].find(f"{NS}path")
        self.assertEqual(hollow.get("fill"), page, "the triangle is hollow")
        self.assertEqual(drawn["diamond"].find(f"{NS}path").get("fill"), edge, "filled")
        self.assertEqual(drawn["open diamond"].find(f"{NS}path").get("fill"), page, "hollow")
        self.assertEqual(drawn["arrow"].find(f"{NS}path").get("fill"), "none", "an open arrow")
        plain = spec(relations=[{"from": "layer", "to": "circle", "type": "association"}])
        self.assertIsNone(lines(draw(plain, "light"))[0].get("marker-end"), "no arrow by default")

    def test_the_markers_touch_the_class_they_belong_to(self):
        svg = draw(SPEC, "light")
        d = numbers(ends_of(svg, "circle", "shape").get("d"))
        l, _, r, b = outline(svg, "shape")
        self.assertTrue(l <= d[-2] <= r and d[-1] == b, "the triangle sits on the parent")
        d = numbers(ends_of(svg, "canvas", "layer").get("d"))
        l, _, r, b = outline(svg, "canvas")
        self.assertTrue(l <= d[0] <= r and d[1] == b, "the diamond sits on the whole")

    def test_multiplicity_and_role_sit_by_their_end(self):
        svg = draw(SPEC, "light")
        d = numbers(ends_of(svg, "canvas", "layer").get("d"))
        found = [(e.text, float(e.get("x")), float(e.get("y")))
                 for e in ET.fromstring(svg).iter(f"{NS}text")]
        for text, (px, py) in (("1", d[:2]), ("layers 1..*", d[-2:])):
            with self.subTest(text=text):
                gap = min(abs(x - px) + abs(y - py) for s, x, y in found if s == text)
                self.assertLess(gap, 40, "beside its end of the line")
        self.assertIn("calls", words(svg))
        self.assertIn("shows", words(svg))

    def test_no_line_crosses_a_class(self):
        for name, found in (("shapes", SPEC), ("example", json.loads(EXAMPLE.read_text()))):
            with self.subTest(diagram=name):
                assert_lines_clear(self, draw(found, "light"))

    def test_every_class_is_colored(self):
        root = ET.fromstring(draw(SPEC, "dark"))
        tints = {tint for _, tint in THEMES["dark"]["kinds"].values()}
        for g in root.iter(f"{NS}g"):
            if g.get("data-box"):
                self.assertIn(g.find(f"{NS}rect").get("fill"), tints)

    def test_light_and_dark_both_draw(self):
        light, dark = draw(SPEC, "light"), draw(SPEC, "dark")
        self.assertNotEqual(light, dark)
        self.assertIn(THEMES["light"]["page"], light)
        self.assertIn(THEMES["dark"]["page"], dark)

    def test_a_bad_spec_says_what_is_wrong(self):
        classes = SPEC["classes"]
        cases = [
            (spec(relations=[{"from": "shape", "to": "nowhere", "type": "uses"}]), "nowhere"),
            (spec(relations=[{"from": "shape", "to": "circle", "type": "likes"}]), "likes"),
            (spec(relations=[{"from": "shape", "to": "circle", "type": "uses", "ends": ["1"]}]),
             "ends"),
            (spec(classes=[dict(classes[0], kind="robot"), *classes[1:]]), "kind"),
            (spec(classes=[dict(classes[0], icon="rocket"), *classes[1:]]), "rocket"),
            (spec(classes=[*classes, dict(classes[0], id="again")]), "share col"),
            (spec(classes=[*classes, dict(classes[1])]), "two classes"),
            (spec(classes=[dict(classes[0], name=""), *classes[1:]]), "name"),
            (spec(classes=[]), "no classes"),
            (spec(title=""), "title"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_class_cannot_inherit_from_itself_or_in_a_circle(self):
        rels = SPEC["relations"]
        cases = [
            (spec(relations=[*rels, {"from": "shape", "to": "shape", "type": "inherits"}]),
             "itself"),
            (spec(relations=[*rels, {"from": "drawable", "to": "drawable",
                                     "type": "implements"}]), "itself"),
            (spec(relations=[*rels, {"from": "shape", "to": "circle", "type": "inherits"}]),
             "circle"),
            (spec(relations=[*rels, {"from": "drawable", "to": "circle", "type": "implements"}]),
             "circle"),
        ]
        for bad, says in cases:
            with self.subTest(bad=bad["relations"][-1]), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_class_may_hold_or_know_itself(self):
        for kind in ("association", "owns"):
            with self.subTest(kind=kind):
                draw(spec(relations=[*SPEC["relations"],
                                     {"from": "layer", "to": "layer", "type": kind}]), "light")

    def test_a_wrong_type_gives_a_plain_error(self):
        classes = SPEC["classes"]
        cases = [
            spec(classes=["Shape"]),
            spec(classes=[dict(classes[0], fields="name"), *classes[1:]]),
            spec(classes=[dict(classes[0], methods=[3]), *classes[1:]]),
            spec(classes=[dict(classes[0], col="1"), *classes[1:]]),
            spec(classes=[dict(classes[0], abstract="yes"), *classes[1:]]),
            spec(relations=["shape -> circle"]),
            spec(relations=[{"from": "shape", "to": "circle", "type": "uses", "label": 3}]),
            spec(relations=[{"from": "shape", "to": "circle", "type": "uses", "ends": "1"}]),
            spec(names=["server"]),
            spec(title=5),
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draw(bad, "light")

    def test_no_words_overlap_and_nothing_is_clipped(self):
        for name, found in (("shapes", SPEC), ("example", json.loads(EXAMPLE.read_text()))):
            for theme in ("light", "dark"):
                with self.subTest(diagram=name, theme=theme):
                    assert_clean(self, draw(found, theme))

    def test_the_plan_model_example_draws(self):
        svg = draw(json.loads(EXAMPLE.read_text()), "light")
        for text in ("Plan", "Ticket", "Item", "must: bool"):
            self.assertIn(text, words(svg))


def assert_lines_clear(test, svg):
    """No line passes over a box other than the two it joins."""
    boxes = {g.get("data-box"): outline(svg, g.get("data-box"))
             for g in ET.fromstring(svg).iter(f"{NS}g") if g.get("data-box")}
    for line in lines(svg):
        d = numbers(line.get("d"))
        pts = list(zip(d[::2], d[1::2], strict=True))
        for cid, (l, t, r, b) in boxes.items():
            if cid in (line.get("data-from"), line.get("data-to")):
                continue
            for (x1, y1), (x2, y2) in pairwise(pts):
                inside = (min(x1, x2) < r and max(x1, x2) > l
                          and min(y1, y2) < b and max(y1, y2) > t)
                test.assertFalse(inside, f"{line.get('data-from')} -> {line.get('data-to')} "
                                 f"crosses {cid}")


def assert_clean(test, svg):
    """No two words overlap, no label sits on a box, and nothing is cut off."""
    root = ET.fromstring(svg)
    x0, y0, w, h = (float(v) for v in root.get("viewBox").split())
    boxes = []
    for e in root.iter(f"{NS}text"):
        size = float(e.get("font-size"))
        width = text_width(e.text or "", size, float(e.get("letter-spacing") or 0))
        x, y = float(e.get("x")), float(e.get("y"))
        left = x - width / 2 if e.get("text-anchor") == "middle" else x
        boxes.append((left, y - size * 0.8, left + width, y + size * 0.25, e.text))
    for a in range(len(boxes)):
        l, t, r, b, text = boxes[a]
        test.assertTrue(x0 <= l and r <= x0 + w and y0 <= t and b <= y0 + h, text)
        for l2, t2, r2, b2, other in boxes[a + 1:]:
            test.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, (text, other))

    def edges(r):
        x, y = float(r.get("x")), float(r.get("y"))
        return x, y, x + float(r.get("width")), y + float(r.get("height"))

    frames = [r for r in root.iter(f"{NS}rect") if r.get("class") == "label"]
    outer = [g.find(f"{NS}rect") for g in root.iter(f"{NS}g") if g.get("data-box")]
    for i, f in enumerate(frames):
        l, t, r, b = edges(f)
        for other in frames[i + 1:] + outer:
            l2, t2, r2, b2 = edges(other)
            test.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, "a label on a box")
    # Words outside the boxes (end texts) stay off every box.
    inside = {id(e) for g in root.iter(f"{NS}g") if g.get("data-box")
              for e in g.iter(f"{NS}text")}
    for e in root.iter(f"{NS}text"):
        if id(e) in inside or e.get("class") != "end":
            continue
        size = float(e.get("font-size"))
        x, y = float(e.get("x")), float(e.get("y"))
        r_ = x + text_width(e.text, size)
        for box in outer:
            l2, t2, r2, b2 = edges(box)
            test.assertFalse(x < r2 and l2 < r_ and y - size * 0.8 < b2 and t2 < y + size * 0.25,
                             f"{e.text} sits on a box")
    for p in root.iter(f"{NS}path"):
        if p.get("class") == "relation":
            d = numbers(p.get("d"))
            for x, y in zip(d[::2], d[1::2], strict=True):
                test.assertTrue(x0 <= x <= x0 + w and y0 <= y <= y0 + h, "a line is cut off")


if __name__ == "__main__":
    unittest.main()
