"""A C4 diagram with "style": "isometric": the same spec, drawn as a scene,
with the layout worked out from the grid. Tested through diagram.draw."""

import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET

from diagram import draw
from diagram.flow import THEMES, text_width
from tests.test_diagram_c4 import CONTAINER, CONTEXT, DEPLOYMENT, DYNAMIC, SRC

NS = "{http://www.w3.org/2000/svg}"
LEVELS = {"context": CONTEXT, "container": CONTAINER, "component": dict(CONTAINER,
                                                                         level="component"),
          "dynamic": DYNAMIC, "deployment": DEPLOYMENT}
EXAMPLES = ("c4-context", "c4-container", "c4-dynamic", "c4-deployment")


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
            motions = root.findall(f".//{NS}animateMotion")
            self.assertEqual(len(motions), 1, "one dot")
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", motions[0].get("path"))]
            path = list(zip(nums[::2], nums[1::2], strict=True))
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

    def test_an_unknown_style_gives_a_plain_error(self):
        for bad in ("3d", 5):
            with self.subTest(style=bad), self.assertRaises(ValueError) as err:
                draw(dict(CONTEXT, style=bad), "light")
            self.assertIn("style", str(err.exception))


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
