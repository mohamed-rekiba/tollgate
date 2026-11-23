"""The use case kind: actors, the use cases inside one system's border, plain
links, and «include» and «extend», drawn through diagram.draw."""

import copy
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram import draw
from diagram.flow import THEMES
from tests.test_diagram_c4 import assert_clean, rect_of, where, words

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src" / "usecase.json"
NS = "{http://www.w3.org/2000/svg}"

SPEC = {
    "type": "usecase", "title": "A library", "desc": "A reader borrows a book; a clerk adds books.",
    "system": "The library",
    "actors": [
        {"id": "reader", "name": "Reader", "col": 0, "row": 0},
        {"id": "clerk", "name": "Clerk", "description": "Works at the desk", "col": 0, "row": 1,
         "kind": "advisor"},
    ],
    "cases": [
        {"id": "borrow", "name": "Borrow a book", "col": 1, "row": 0},
        {"id": "card", "name": "Show a card", "col": 2, "row": 0, "kind": "check"},
        {"id": "late", "name": "Pay a fine", "col": 2, "row": 1, "kind": "advisor"},
        {"id": "add", "name": "Add a book", "col": 1, "row": 1},
    ],
    "links": [
        {"from": "reader", "to": "borrow"},
        {"from": "clerk", "to": "add"},
        {"from": "borrow", "to": "card", "type": "include"},
        {"from": "late", "to": "borrow", "type": "extend"},
    ],
}


def spec(**change):
    out = copy.deepcopy(SPEC)
    out.update(change)
    return out


class UseCaseTest(unittest.TestCase):
    def test_actors_and_cases_draw_with_their_words(self):
        svg = draw(SPEC, "light")
        for text in ("Reader", "Clerk", "Works at the desk", "Borrow a book", "Show a card",
                     "Pay a fine", "Add a book", "The library"):
            self.assertIn(text, words(svg))
        root = ET.fromstring(svg)
        self.assertEqual(root.find(f"{NS}title").text, "A library")
        self.assertEqual(len(root.findall(f".//{NS}g[@class='person']")), 2, "actors are people")
        self.assertEqual(len(root.findall(f".//{NS}g[@class='oval']")), 4)
        for oval in root.findall(f".//{NS}g[@class='oval']"):
            self.assertIsNotNone(oval.find(f"{NS}ellipse"), "a use case is an oval")

    def test_the_cases_sit_in_the_system_and_the_actors_outside(self):
        svg = draw(SPEC, "dark")
        (border,) = ET.fromstring(svg).findall(f".//{NS}g[@class='system']")
        l, t, r, b = rect_of(border.find(f"{NS}rect"))
        for case in ("Borrow a book", "Show a card", "Pay a fine", "Add a book"):
            x, y = where(svg, case)
            self.assertTrue(l < x < r and t < y < b, case)
        for actor in ("Reader", "Clerk"):
            x, _ = where(svg, actor)
            self.assertLess(x, l, actor)

    def test_a_link_is_a_plain_line_and_include_and_extend_are_dashed_arrows(self):
        svg = draw(SPEC, "light")
        root = ET.fromstring(svg)
        lines = [p for p in root.iter(f"{NS}path") if p.get("class") == "line"]
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIsNone(line.get("marker-end"), "a link has no head")
        dashed = [p for p in root.iter(f"{NS}path") if p.get("class") == "side"]
        self.assertEqual(len(dashed), 2)
        for arrow in dashed:
            self.assertTrue(arrow.get("marker-end"))
        self.assertIn("«include»", words(svg))
        self.assertIn("«extend»", words(svg))

    def test_every_case_and_actor_is_colored(self):
        neutral = THEMES["light"]["kinds"]["neutral"][0]
        root = ET.fromstring(draw(SPEC, "light"))
        for g in root.iter(f"{NS}g"):
            if g.get("class") in ("person", "oval"):
                self.assertNotEqual(g[0].get("stroke"), neutral)

    def test_light_and_dark_both_draw(self):
        light, dark = draw(SPEC, "light"), draw(SPEC, "dark")
        self.assertIn("#ffffff", light)
        self.assertIn("#0d1117", dark)

    def test_a_bad_spec_says_what_is_wrong(self):
        cases = [
            (spec(links=[{"from": "reader", "to": "nobody"}]), "nobody"),
            (spec(links=[{"from": "reader", "to": "borrow", "type": "uses"}]),
             "type must be one of"),
            (spec(links=[{"from": "reader", "to": "borrow", "type": "include"}]),
             "joins two use cases"),
            (spec(links=[{"from": "borrow", "to": "add"}]), "joins an actor and a use case"),
            (spec(cases=[]), "no use cases"),
            (spec(system=""), "system"),
            (spec(actors=[dict(SPEC["actors"][0], kind="robot"), SPEC["actors"][1]]), "kind"),
            (spec(title=""), "title"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_wrong_type_gives_a_plain_error(self):
        cases = [
            spec(actors="reader"),
            spec(cases=["borrow"]),
            spec(cases=[dict(SPEC["cases"][0], name=5)]),
            spec(actors=[dict(SPEC["actors"][0], row="0")]),
            spec(links=[["reader", "borrow"]]),
            spec(links=[{"from": "reader", "to": "borrow", "type": 1}]),
            spec(system=["The library"]),
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draw(bad, "light")

    def test_no_words_overlap_and_nothing_is_clipped(self):
        for name, s in (("library", SPEC), ("example", json.loads(EXAMPLE.read_text()))):
            for theme in ("light", "dark"):
                with self.subTest(diagram=name, theme=theme):
                    assert_clean(self, draw(s, theme))

    def test_the_example_draws_tollgate(self):
        found = words(draw(json.loads(EXAMPLE.read_text()), "light"))
        for text in ("Tollgate", "Owner", "Approve a change"):
            self.assertIn(text, found)


if __name__ == "__main__":
    unittest.main()
