"""The ER diagram kind: tables with their columns, types and key tags, and
relationships with a crow's foot end at each table."""

import copy
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram import draw
from diagram.flow import THEMES
from tests.test_diagram_class import (
    NS,
    assert_clean,
    assert_lines_clear,
    ends_of,
    lines,
    marker,
    outline,
    words,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src" / "store-records.json"

SPEC = {
    "type": "er", "title": "A library", "desc": "Members borrow books; each loan has one book.",
    "names": {"server": "Library"},
    "tables": [
        {"id": "member", "name": "members", "col": 0, "row": 0, "kind": "you",
         "columns": [{"name": "id", "type": "int", "key": "pk"},
                     {"name": "name", "type": "text"}]},
        {"id": "loan", "name": "loans", "col": 1, "row": 0, "kind": "server",
         "columns": [{"name": "member", "type": "int", "key": "pk fk"},
                     {"name": "book", "type": "int", "key": "pk fk"},
                     {"name": "due", "type": "date"}]},
        {"id": "book", "name": "books", "col": 2, "row": 0, "kind": "ai", "icon": "plan",
         "columns": [{"name": "id", "type": "int", "key": "pk"},
                     {"name": "title", "type": "text"}]},
        {"id": "card", "name": "cards", "col": 0, "row": 1, "kind": "check",
         "columns": [{"name": "member", "type": "int", "key": "pk fk"}]},
        {"id": "review", "name": "reviews", "col": 2, "row": 1, "kind": "advisor",
         "columns": [{"name": "book", "type": "int", "key": "fk"},
                     {"name": "stars", "type": "int"}]},
    ],
    "relations": [
        {"from": "member", "to": "loan", "ends": ["exactly one", "zero or many"],
         "label": "borrows"},
        {"from": "loan", "to": "book", "ends": ["one or many", "one"]},
        {"from": "member", "to": "card", "ends": ["one", "zero or one"], "label": "holds"},
        {"from": "book", "to": "review", "ends": ["exactly one", "many"]},
    ],
}


def spec(**change):
    out = copy.deepcopy(SPEC)
    out.update(change)
    return out


class ErTest(unittest.TestCase):
    def test_every_table_draws_its_name_and_columns_with_types(self):
        svg = draw(SPEC, "light")
        for text in ("members", "loans", "books", "due", "date", "title", "text", "stars",
                     "YOU", "LIBRARY", "borrows", "holds"):
            self.assertIn(text, words(svg))
        self.assertEqual(ET.fromstring(svg).find(f"{NS}title").text, "A library")

    def test_keys_are_tagged_pk_and_fk(self):
        root = ET.fromstring(draw(SPEC, "light"))

        def tagged(tid):
            group = root.find(f".//{NS}g[@data-box='{tid}']")
            return [e.text for e in group.iter(f"{NS}text") if e.text in ("PK", "FK")]

        self.assertEqual(tagged("member"), ["PK"])
        self.assertEqual(tagged("loan"), ["PK", "FK", "PK", "FK"])
        self.assertEqual(tagged("review"), ["FK"])

    def test_each_end_is_its_crows_foot(self):
        svg = draw(SPEC, "light")
        cases = [("member", "loan", "exactly one", "zero or many"),
                 ("loan", "book", "one or many", "exactly one"),
                 ("member", "card", "exactly one", "zero or one"),
                 ("book", "review", "exactly one", "zero or many")]
        for a, b, start, end in cases:
            with self.subTest(relation=f"{a} -> {b}"):
                line = ends_of(svg, a, b)
                self.assertIsNone(line.get("stroke-dasharray"))
                self.assertEqual(marker(svg, line.get("marker-start")).get("data-end"), start)
                self.assertEqual(marker(svg, line.get("marker-end")).get("data-end"), end)
        root = ET.fromstring(svg)

        def parts(name):
            m = root.find(f".//{NS}marker[@data-end='{name}']")
            return (len(m.findall(f"{NS}circle")), m.find(f"{NS}path").get("d"))

        rings, bars = parts("exactly one")
        self.assertEqual((rings, bars.count("V")), (0, 2), "two bars")
        rings, bars = parts("zero or one")
        self.assertEqual((rings, bars.count("V")), (1, 1), "a ring and a bar")
        rings, foot = parts("one or many")
        self.assertEqual((rings, foot.count("V"), foot.count("L")), (0, 1, 2), "a bar and a foot")
        rings, foot = parts("zero or many")
        self.assertEqual((rings, foot.count("V"), foot.count("L")), (1, 0, 2), "a ring and a foot")

    def test_an_end_touches_its_table(self):
        svg = draw(SPEC, "light")
        line = [float(v) for v in ends_of(svg, "member", "loan").get("d")
                .replace("M", " ").replace("L", " ").replace(",", " ").split()]
        self.assertEqual(line[0], outline(svg, "member")[2])
        self.assertEqual(line[-2], outline(svg, "loan")[0])

    def test_a_relation_to_its_own_table_loops_out_and_back(self):
        loop = {"from": "book", "to": "book", "ends": ["zero or one", "many"], "label": "sequel"}
        svg = draw(spec(relations=[loop]), "light")
        line = [float(v) for v in ends_of(svg, "book", "book").get("d")
                .replace("M", " ").replace("L", " ").replace("Q", " ").replace(",", " ").split()]
        t = outline(svg, "book")[1]
        self.assertEqual((line[1], line[-1]), (t, t), "both ends on the top of the table")
        self.assertGreaterEqual(abs(line[-2] - line[0]), 40, "room for an end on each leg")
        self.assertLess(min(line[1::2]), t - 26, "it reaches out past both markers")
        assert_clean(self, svg)

    def test_every_table_is_colored(self):
        root = ET.fromstring(draw(SPEC, "light"))
        tints = {tint for _, tint in THEMES["light"]["kinds"].values()}
        for g in root.iter(f"{NS}g"):
            if g.get("data-box"):
                self.assertIn(g.find(f"{NS}rect").get("fill"), tints)

    def test_light_and_dark_both_draw(self):
        light, dark = draw(SPEC, "light"), draw(SPEC, "dark")
        self.assertNotEqual(light, dark)
        self.assertIn(THEMES["dark"]["page"], dark)

    def test_a_bad_spec_says_what_is_wrong(self):
        tables = SPEC["tables"]
        rel = SPEC["relations"][0]
        cases = [
            (spec(relations=[dict(rel, to="nowhere")]), "nowhere"),
            (spec(relations=[dict(rel, ends=["one", "lots"])]), "zero or many"),
            (spec(relations=[{"from": "member", "to": "loan"}]), "needs 'ends'"),
            (spec(tables=[dict(tables[0], columns=[{"name": "id", "key": "primary"}]),
                          *tables[1:]]), "pk"),
            (spec(tables=[dict(tables[0], columns=[]), *tables[1:]]), "columns"),
            (spec(tables=[dict(tables[0], kind="robot"), *tables[1:]]), "kind"),
            (spec(tables=[*tables, dict(tables[0], id="again")]), "share col"),
            (spec(tables=[]), "no tables"),
            (spec(desc=""), "desc"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_wrong_type_gives_a_plain_error(self):
        tables = SPEC["tables"]
        cases = [
            spec(tables="members"),
            spec(tables=[dict(tables[0], columns="id"), *tables[1:]]),
            spec(tables=[dict(tables[0], columns=[{"name": 1}]), *tables[1:]]),
            spec(tables=[dict(tables[0], row=None), *tables[1:]]),
            spec(relations=[dict(SPEC["relations"][0], ends="one")]),
            spec(relations=[dict(SPEC["relations"][0], shift="up")]),
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draw(bad, "light")

    def test_no_words_overlap_nothing_is_clipped_and_no_line_crosses_a_table(self):
        for name, found in (("library", SPEC), ("example", json.loads(EXAMPLE.read_text()))):
            for theme in ("light", "dark"):
                svg = draw(found, theme)
                with self.subTest(diagram=name, theme=theme):
                    assert_clean(self, svg)
                    self.assertTrue(lines(svg))
                    assert_lines_clear(self, svg)

    def test_the_store_records_example_draws(self):
        svg = draw(json.loads(EXAMPLE.read_text()), "light")
        for text in ("locks", "passes", "approvals", "PK", "FK"):
            self.assertIn(text, words(svg))


if __name__ == "__main__":
    unittest.main()
