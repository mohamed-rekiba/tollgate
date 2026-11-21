"""AWS icons: the loader finds icons by short name, and a diagram inlines them."""

import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from driver import aws
from driver.diagram import draw
from setup import aws_icons

PACK = str(Path(__file__).parent / "fixtures" / "aws-pack")


class AwsIconsTest(unittest.TestCase):
    def setUp(self):
        aws.index.cache_clear()

    def test_finds_by_short_name_and_prefers_48(self):
        path = aws._find("service", "s3", PACK)
        self.assertTrue(path.name.endswith("_48.svg"))
        self.assertIn("Lambda", aws._find("service", "lambda", PACK).name)

    def test_inline_prefixes_ids_and_drops_the_header(self):
        svg = aws.service("s3", prefix="n1", root=PACK)
        self.assertFalse(svg.startswith("<?xml"))
        self.assertIn('id="n1-g1"', svg)
        self.assertIn("url(#n1-g1)", svg)

    def test_group_color_comes_from_its_icon(self):
        _, color, dashed = aws.group("vpc", root=PACK)
        self.assertEqual(color.upper(), "#8C4FFF")
        self.assertFalse(dashed)
        self.assertTrue(aws.group("region", root=PACK)[2])

    def test_missing_pack_says_how_to_get_it(self):
        with self.assertRaises(aws.Missing) as err:
            aws.index("/nowhere/at/all")
        self.assertIn("setup.aws_icons", str(err.exception))

    def test_a_diagram_with_aws_groups_and_icons(self):
        spec = {"title": "A web app", "desc": "An API in front of a function and a table.",
                "nodes": [{"id": "api", "text": "API Gateway", "col": 0, "row": 0, "aws": "apigw"},
                          {"id": "fn", "text": "Lambda\nthe handler", "col": 1, "row": 0,
                           "aws": "lambda"},
                          {"id": "db", "text": "DynamoDB", "col": 2, "row": 0, "aws": "dynamodb"}],
                "edges": [{"from": "api", "to": "fn"}, {"from": "fn", "to": "db"}],
                "groups": [{"label": "AWS Cloud", "nodes": ["api", "fn", "db"], "aws": "cloud"},
                           {"label": "us-east-1", "nodes": ["fn", "db"], "aws": "region"}]}
        old = aws.CACHE
        aws.CACHE = Path(PACK)
        try:
            svg = draw(spec, "light")
        finally:
            aws.CACHE = old
        root = ET.fromstring(svg)
        nested = root.findall("{http://www.w3.org/2000/svg}svg")
        self.assertEqual(len(nested), 5)  # 3 services, 2 groups
        ids = [e.get("id") for e in root.iter() if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)), "ids clash")

    def test_unpack_reads_nested_zips_and_skips_bad_paths(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z:
            z.writestr("Group/Region_32.svg", "<svg/>")
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, "w") as z:
            z.writestr("Service/Arch_AWS-Lambda_48.svg", "<svg/>")
            z.writestr("groups.zip", inner.getvalue())
            z.writestr("../evil.svg", "<svg/>")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(aws_icons.unpack(outer.getvalue(), Path(d)), 2)
            self.assertFalse(Path(d).parent.joinpath("evil.svg").exists())


if __name__ == "__main__":
    unittest.main()
