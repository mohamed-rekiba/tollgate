"""The diagram package: flowchart shapes, scenes from a spec, the build command,
and fetching the AWS icons on first use."""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
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
