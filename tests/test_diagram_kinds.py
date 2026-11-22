"""The diagram package: flowchart shapes, scenes from a spec, the build command,
and fetching the AWS icons on first use."""

import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from itertools import pairwise
from pathlib import Path
from unittest import mock

from diagram import aws, draw, flow, scene
from diagram.__main__ import build

NS = "{http://www.w3.org/2000/svg}"


def words(svg):
    return " ".join(e.text or "" for e in ET.fromstring(svg).iter())


class ShapesTest(unittest.TestCase):
    def test_every_shape_draws_with_its_text(self):
        nodes = [{"id": s, "text": f"{s} title\nline", "col": i % 4, "row": i // 4, "shape": s}
                 for i, s in enumerate(flow.SHAPES)]
        svg = draw({"title": "Shapes", "desc": "Every shape.", "nodes": nodes, "edges": []},
                   "light")
        for s in flow.SHAPES:
            self.assertIn(f"{s} title", words(svg))
        root = ET.fromstring(svg)
        self.assertTrue(root.findall(f".//{NS}polygon"), "the diamond, slant, and trapezoid")
        self.assertTrue(root.findall(f".//{NS}ellipse") or "A" in svg)

    def test_a_diamond_keeps_its_height_and_a_pill_its_own(self):
        spec = {"title": "t", "desc": "d", "edges": [],
                "nodes": [{"id": "a", "text": "Start\nhere", "col": 0, "row": 0, "shape": "start"},
                          {"id": "q", "text": "Pass?\nthe tests\non the server", "col": 1,
                           "row": 0, "shape": "decision"}]}
        boxes = flow.layout(spec)
        pill = boxes["a"]["b"] - boxes["a"]["t"]
        diamond = boxes["q"]["b"] - boxes["q"]["t"]
        self.assertGreater(diamond, pill)
        self.assertAlmostEqual(boxes["a"]["y"], boxes["q"]["y"], delta=1)


class SceneTest(unittest.TestCase):
    def test_every_object_draws_from_a_spec(self):
        objects = [{"type": t, "at": [i * 60 - 300, 0]} for i, t in enumerate(scene.OBJECTS)
                   if t not in ("zone", "aws")]
        for o in objects:
            if o["type"] == "gate":
                o["arm_to"] = o["at"][0] - 40
            if o["type"] == "wall":
                o["to"] = [o["at"][0] + 10, 60]
        spec = {"type": "scene", "title": "Every object", "desc": "d",
                "zones": [{"at": [-320, -60, 320, 60]}], "objects": objects,
                "lanes": [{"path": [[-300, 80], [300, 80]], "label": "a lane"}],
                "labels": [{"at": [0, 0, 100], "head": "Hello", "sub": ["one", "two"]}],
                "ticket": {"legs": [{"path": [[-300, 80], [0, 80]], "wait": 0.5},
                                    {"path": [[0, 80], [300, 80]], "tone": "pass"}], "lift": 1}}
        for theme in ("light", "dark"):
            svg = draw(spec, theme)
            root = ET.fromstring(svg)
            self.assertEqual(root.get("role"), "img")
            self.assertIn("HELLO", words(svg))
            self.assertIn("prefers-reduced-motion", svg)

    def test_an_unknown_object_says_which_ones_exist(self):
        spec = {"type": "scene", "title": "t", "desc": "d", "objects": [{"type": "rocket",
                                                                          "at": [0, 0]}]}
        with self.assertRaises(ValueError) as err:
            draw(spec, "light")
        self.assertIn("room", str(err.exception))


def callout_spec(callouts, size=(600, 400)):
    return {"type": "scene", "title": "t", "desc": "d", "size": list(size),
            "origin": [300, 200], "scale": 0.6, "callouts": callouts}


LEFT = [{"n": 1, "head": "Low", "line": "The lowest point.", "to": [0, 200, 0], "side": "left"},
        {"n": 2, "head": "Mid", "line": "A point in the middle of the scene.",
         "to": [0, 0, 0], "side": "left", "kind": "ai"},
        {"n": 3, "head": "High", "line": "The highest point.", "to": [0, -200, 0], "side": "left"}]
RIGHT = [{"n": 4, "head": "Top", "line": "Near the top.", "to": [200, -100, 0], "side": "right"},
         {"n": 5, "head": "Close", "line": "Close to the one above it.", "to": [200, -90, 0],
          "side": "right", "kind": "check"},
         {"n": 6, "head": "Down", "line": "Far down.", "to": [200, 150, 0], "side": "right"}]
UNDER = [{"n": 7, "head": "Always", "line": "Under the scene.", "side": "bottom"}]


def texts(svg):
    root = ET.fromstring(svg)
    return [(float(e.get("x")), float(e.get("y")), e.text) for e in root.iter(f"{NS}text")]


def places(callouts, size=(600, 400)):
    s = scene.Scene("light", size[0] + 2 * scene.COLUMN, size[1], (300 + scene.COLUMN, 200), 0.6)
    frame = (scene.COLUMN, 24, scene.COLUMN + size[0], size[1] - 16)
    return scene.callout_layout(callouts, s.iso, frame), frame


class CalloutTest(unittest.TestCase):
    def test_the_page_widens_for_each_column_and_the_bottom_row(self):
        for callouts, grow_w, grow_h in ((LEFT, scene.COLUMN, 0),
                                         (LEFT + RIGHT, 2 * scene.COLUMN, 0),
                                         (LEFT + RIGHT + UNDER, 2 * scene.COLUMN, scene.BOTTOM),
                                         ([], 0, 0)):
            root = ET.fromstring(draw(callout_spec(callouts), "light"))
            self.assertEqual(root.get("viewBox"), f"0 0 {600 + grow_w} {400 + grow_h}")

    def test_each_label_sits_in_its_column_with_a_leader_to_its_point(self):
        out, (left, _, right, _) = places(LEFT + RIGHT)
        for c in LEFT + RIGHT:
            x, _, point = out[c["n"]]
            self.assertLess(x, left) if c["side"] == "left" else self.assertGreater(x, right)
            self.assertIsNotNone(point)
        svg = draw(callout_spec(LEFT + RIGHT + UNDER), "dark")
        root = ET.fromstring(svg)
        dotted = [e for e in root.iter(f"{NS}line") if e.get("stroke-dasharray") == "1 4"]
        self.assertEqual(len(dotted), len(LEFT + RIGHT), "a leader for each, none for the bottom")
        for head in ("LOW", "MID", "HIGH", "TOP", "CLOSE", "DOWN", "ALWAYS"):
            self.assertIn(head, words(svg))

    def test_labels_in_a_column_never_overlap(self):
        out, _ = places(LEFT + RIGHT)
        for side in ("left", "right"):
            column = sorted((c for c in LEFT + RIGHT if c["side"] == side),
                            key=lambda c: out[c["n"]][1])
            for a, b in pairwise(column):
                bottom_of_a = out[a["n"]][1] + scene.callout_height(a)
                self.assertLessEqual(bottom_of_a + scene.BADGE, out[b["n"]][1])

    def test_leaders_in_a_column_never_cross(self):
        # 5 is numbered above 6 but its point is lower: the labels move apart until
        # the two leaders clear each other.
        tricky = [{"n": 1, "head": "A", "line": "a far point", "to": [-150, -150, 0],
                   "side": "right"},
                  {"n": 2, "head": "B", "line": "a near point", "to": [300, 0, 0],
                   "side": "right"}]
        out, _ = places(tricky)
        (xa, ya, pa), (xb, yb, pb) = out[1], out[2]
        self.assertLess(ya, yb)
        self.assertFalse(scene.crosses((xa, ya), pa, (xb, yb), pb))
        out, _ = places(LEFT + RIGHT)
        for side in ("left", "right"):
            ns = [c["n"] for c in LEFT + RIGHT if c["side"] == side]
            for i in ns:
                for j in ns:
                    if i < j:
                        (x1, y1, p1), (x2, y2, p2) = out[i], out[j]
                        self.assertFalse(scene.crosses((x1, y1), p1, (x2, y2), p2), (i, j))

    def test_numbers_run_clockwise(self):
        out, _ = places(LEFT + RIGHT)
        self.assertGreater(out[1][1], out[2][1], "the left column reads upward")
        self.assertGreater(out[2][1], out[3][1])
        self.assertLess(out[4][1], out[5][1], "the right column reads downward")
        self.assertLess(out[5][1], out[6][1])
        backward = [dict(c, n=c["n"] + 1) for c in LEFT] + [dict(UNDER[0], n=1)]
        with self.assertRaises(ValueError) as err:
            draw(callout_spec(backward), "light")
        self.assertIn("clockwise", str(err.exception))

    def test_a_bottom_callout_is_centered_under_the_scene(self):
        svg = draw(callout_spec(LEFT + RIGHT + UNDER), "light")
        (head,) = [t for t in texts(svg) if t[2] == "ALWAYS"]
        self.assertGreater(head[1], 400, "under the scene")
        width = scene.bottom_width(UNDER[0])
        center = scene.COLUMN + 300
        self.assertAlmostEqual(head[0], center - width / 2 + 2 * scene.BADGE + 12, delta=1)

    def test_a_line_that_wraps_past_two_lines_is_refused(self):
        long = [dict(LEFT[0], line="word " * 40)]
        with self.assertRaises(ValueError) as err:
            draw(callout_spec(long), "light")
        self.assertIn("shorten", str(err.exception))
        for bad, says in (({"side": "up"}, "side"), ({"to": None}, "to"), ({"kind": "x"}, "kind")):
            with self.subTest(bad=bad), self.assertRaises(ValueError) as err:
                draw(callout_spec([dict(LEFT[0], **bad)]), "light")
            self.assertIn(says, str(err.exception))

    def test_the_how_it_works_picture_numbers_every_rule(self):
        """One picture holds the process and the rules: numbers 1 to 8, each once."""
        import re
        root = Path(__file__).resolve().parent.parent / "docs" / "diagrams"
        for name in ("how-it-works.svg", "how-it-works-dark.svg"):
            svg = (root / name).read_text()
            found = sorted(int(n) for n in re.findall(r'class="pin" data-n="(\d+)"', svg))
            self.assertEqual(found, list(range(1, 9)), name)


def pin_spec(label, **extra):
    return {"type": "scene", "title": "t", "desc": "d", "size": [600, 400],
            "origin": [300, 200], "scale": 0.6, "labels": [label], **extra}


class PinTest(unittest.TestCase):
    def stem(self, svg):
        group = ET.fromstring(svg).find(f".//{NS}g[@class='pin']")
        return group, [float(v) for v in re.findall(r"-?\d+\.\d", group.find(f"{NS}path").get("d"))]

    def test_a_straight_stem_stops_at_the_edge_of_its_number(self):
        for drop in (60, -60):
            svg = draw(pin_spec({"n": 3, "head": "Build", "sub": "x", "pin": [0, 0, 0],
                                 "drop": drop, "kind": "ai"}), "light")
            group, d = self.stem(svg)
            number = group.find(f"{NS}circle[@r='{scene.BADGE}']")
            cx, cy = float(number.get("cx")), float(number.get("cy"))
            with self.subTest(drop=drop):
                self.assertEqual(d[0], cx, "the number sits on the stem")
                self.assertEqual(abs(d[-1] - cy), scene.BADGE + 2, "the stem stops at its edge")

    def test_a_number_close_to_the_stem_moves_onto_it(self):
        svg = draw(pin_spec({"n": 6, "head": "Main", "sub": "x", "pin": [0, 0, 0],
                             "at": [10, -10, -60], "anchor": "start", "kind": "you"}), "light")
        group, d = self.stem(svg)
        number = group.find(f"{NS}circle[@r='{scene.BADGE}']")
        self.assertEqual(float(number.get("cx")), d[0])
        words = group.find(f"{NS}text[@letter-spacing]")
        self.assertEqual(float(words.get("x")) - d[0], scene.PIN_GAP)

    def test_a_level_route_leaves_the_pin_sideways_first(self):
        svg = draw(pin_spec({"n": 2, "head": "Gate", "sub": "x", "pin": [0, 0, 0],
                             "at": [200, -200, 120], "anchor": "start", "kind": "check",
                             "route": "level"}), "light")
        _, d = self.stem(svg)
        x0, y0, x1, y1 = d[0], d[1], d[2], d[3]
        self.assertEqual(y1, y0, "the first leg is level")
        self.assertNotEqual(x1, x0)

    def test_the_rings_stop_pulsing_on_request(self):
        svg = draw(pin_spec({"n": 1, "head": "Plan", "pin": [0, 0, 0], "drop": 50}), "dark")
        self.assertIn('class="pulse"', svg)
        self.assertRegex(svg, r"prefers-reduced-motion:reduce\)\{[^}]*\.pulse\{animation:none")

    def test_a_pinned_label_needs_a_place(self):
        with self.assertRaisesRegex(ValueError, "give it 'at' or 'drop'"):
            draw(pin_spec({"head": "Lost", "pin": [0, 0, 0]}), "light")

    def test_the_note_has_its_number(self):
        svg = draw(pin_spec({"head": "x", "at": [0, 0, 0]}, caption=["A", "b"],
                            note={"n": 8, "head": "Always", "line": "every rule"}), "light")
        self.assertIn('class="pin" data-n="8"', svg)
        self.assertIn("ALWAYS", svg)


class BuildTest(unittest.TestCase):
    def test_build_draws_both_themes_and_check_sees_drift(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d, "src")
            src.mkdir()
            spec = {"title": "One step", "desc": "d",
                    "nodes": [{"id": "a", "text": "A step", "col": 0, "row": 0}], "edges": []}
            (src / "one.json").write_text(json.dumps(spec))
            self.assertEqual(sorted(build(d)), ["one-dark.svg", "one.svg"])
            self.assertEqual(build(d, check=True), [])
            spec["nodes"][0]["text"] = "Another step"
            (src / "one.json").write_text(json.dumps(spec))
            self.assertEqual(len(build(d, check=True)), 2)


class AwsFetchTest(unittest.TestCase):
    def setUp(self):
        aws.index.cache_clear()

    def test_the_cache_is_fetched_once_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d, "icons")
            pack = Path(__file__).parent / "fixtures" / "aws-pack"

            def fake_fetch(url=aws.URL, target=None):
                import shutil
                shutil.copytree(pack, cache)
                return 1

            with mock.patch.object(aws, "CACHE", cache), \
                    mock.patch.object(aws, "fetch", side_effect=fake_fetch) as fetched:
                aws.service("s3")
                aws.service("lambda")
            self.assertEqual(fetched.call_count, 1)

    def test_no_fetch_when_turned_off(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(aws, "CACHE", Path(d, "icons")), \
                mock.patch.dict("os.environ", {"TOLLGATE_AWS_ICONS_FETCH": "0"}), \
                mock.patch.object(aws, "fetch") as fetched:
            with self.assertRaises(aws.Missing):
                aws.service("s3")
            fetched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
