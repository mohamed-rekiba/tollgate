"""The C4 kind: a context, container, component, dynamic, or deployment diagram,
built on the flow and drawn through diagram.draw."""

import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram import draw
from diagram.flow import THEMES, text_width

SRC = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src"
NS = "{http://www.w3.org/2000/svg}"


def words(svg):
    return [e.text or "" for e in ET.fromstring(svg).iter(f"{NS}text")]


def where(svg, text):
    """The left and the baseline of the first text that says `text`."""
    for e in ET.fromstring(svg).iter(f"{NS}text"):
        if e.text == text:
            return float(e.get("x")), float(e.get("y"))
    raise AssertionError(f"'{text}' is not drawn")


def rect_of(e):
    x, y = float(e.get("x")), float(e.get("y"))
    return x, y, x + float(e.get("width")), y + float(e.get("height"))


CONTEXT = {
    "type": "c4", "level": "context", "title": "A shop",
    "desc": "A buyer uses the shop, which takes payment through a bank.",
    "elements": [
        {"id": "buyer", "type": "person", "name": "Buyer",
         "description": "Someone who buys", "col": 0, "row": 0},
        {"id": "shop", "type": "system", "name": "The shop",
         "description": "Sells things online", "col": 1, "row": 0},
        {"id": "bank", "type": "system", "external": True, "name": "The bank",
         "description": "Moves the money", "col": 2, "row": 0},
    ],
    "relations": [
        {"from": "buyer", "to": "shop", "label": "Buys from", "tech": "the web"},
        {"from": "shop", "to": "bank", "label": "Takes payment"},
    ],
}

CONTAINER = {
    "type": "c4", "level": "container", "title": "The shop",
    "desc": "Inside the shop: a web app, its database, and a queue of orders.",
    "names": {"server": "The shop"},
    "boundaries": [{"id": "shop", "name": "The shop", "type": "Software System"}],
    "elements": [
        {"id": "buyer", "type": "person", "name": "Buyer", "col": 0, "row": 0},
        {"id": "web", "type": "container", "name": "Web app", "tech": "Python",
         "description": "Shows the goods", "col": 1, "row": 0, "parent": "shop"},
        {"id": "db", "type": "database", "name": "Orders", "tech": "SQLite",
         "description": "Every order", "col": 1, "row": 1, "parent": "shop"},
        {"id": "q", "type": "queue", "name": "To ship", "tech": "Files",
         "description": "Orders to send", "col": 2, "row": 1, "parent": "shop"},
        {"id": "bank", "type": "system", "external": True, "name": "The bank",
         "col": 3, "row": 0},
    ],
    "relations": [
        {"from": "buyer", "to": "web", "label": "Buys from", "tech": "HTTPS"},
        {"from": "web", "to": "db", "label": "Writes the order", "tech": "SQL"},
        {"from": "db", "to": "q", "label": "Sends on"},
        {"from": "web", "to": "bank", "label": "Takes payment", "tech": "HTTPS"},
    ],
}

DYNAMIC = {
    "type": "c4", "level": "dynamic", "title": "One order",
    "desc": "A buyer orders, the web app saves it, then asks the bank.",
    "boundaries": CONTAINER["boundaries"],
    "elements": CONTAINER["elements"][:3] + [CONTAINER["elements"][4]],
    "relations": [
        {"from": "buyer", "to": "web", "label": "Orders"},
        {"from": "web", "to": "db", "label": "Saves it", "tech": "SQL"},
        {"from": "web", "to": "bank", "label": "Asks for payment"},
    ],
}

DEPLOYMENT = {
    "type": "c4", "level": "deployment", "title": "The shop",
    "desc": "The web app runs in a container on a server, the bank on its own.",
    "boundaries": [
        {"id": "server", "name": "A server", "type": "device"},
        {"id": "docker", "name": "Docker", "type": "execution environment",
         "parent": "server"},
    ],
    "elements": [
        {"id": "web", "type": "container", "name": "Web app", "tech": "Python",
         "col": 0, "row": 0, "parent": "docker", "kind": "ai"},
        {"id": "db", "type": "database", "name": "Orders", "tech": "SQLite",
         "col": 0, "row": 1, "parent": "server"},
        {"id": "bank", "type": "node", "name": "The bank", "stereotype": "device",
         "external": True, "col": 1, "row": 0},
    ],
    "relations": [
        {"from": "web", "to": "db", "label": "Writes", "tech": "SQL"},
        {"from": "web", "to": "bank", "label": "Takes payment"},
    ],
}

EXAMPLES = ("c4-context", "c4-container", "c4-component", "c4-dynamic", "c4-deployment")


def spec(base, **change):
    out = copy.deepcopy(base)
    out.update(change)
    return out


class C4Test(unittest.TestCase):
    def test_each_element_shows_its_name_its_type_and_its_description(self):
        svg = draw(CONTEXT, "light")
        for text in ("Buyer", "[Person]", "Someone who buys", "The shop", "[Software System]",
                     "Sells things online", "The bank", "[External System]"):
            self.assertIn(text, words(svg))
        root = ET.fromstring(svg)
        self.assertEqual(root.get("role"), "img")
        self.assertEqual(root.find(f"{NS}title").text, "System Context diagram for A shop")

    def test_the_level_names_the_diagram(self):
        for base, title in ((CONTAINER, "Container diagram for The shop"),
                            (DYNAMIC, "Dynamic diagram for One order"),
                            (DEPLOYMENT, "Deployment diagram for The shop")):
            svg = draw(base, "light")
            with self.subTest(title=title):
                self.assertIn(title, words(svg), "the title is drawn")
                self.assertEqual(ET.fromstring(svg).find(f"{NS}title").text, title)
        svg = draw(spec(CONTAINER, level="component"), "light")
        self.assertIn("Component diagram for The shop", words(svg))

    def test_a_relation_says_what_then_how_in_brackets(self):
        svg = draw(CONTAINER, "light")
        found = words(svg)
        self.assertIn("Writes the order", found)
        self.assertIn("[SQL]", found)
        self.assertIn("Sends on", found)
        what, how = where(svg, "Writes the order"), where(svg, "[SQL]")
        self.assertGreater(how[1], what[1], "the how sits on its own line, under the what")

    def test_a_container_shows_its_technology(self):
        found = words(draw(CONTAINER, "dark"))
        for text in ("[Container: Python]", "[Container: SQLite]", "[Container: Files]"):
            self.assertIn(text, found)

    def test_a_person_has_a_head_over_its_shoulders(self):
        root = ET.fromstring(draw(CONTEXT, "light"))
        (person,) = root.findall(f".//{NS}g[@class='person']")
        head = person.find(f"{NS}circle")
        body = person.find(f"{NS}rect")
        _, top, _, _ = rect_of(body)
        self.assertLess(float(head.get("cy")), top, "the head sits on top of the body")

    def test_a_database_is_a_cylinder_and_a_queue_is_a_pipe(self):
        root = ET.fromstring(draw(CONTAINER, "light"))
        self.assertEqual(len(root.findall(f".//{NS}g[@class='data']")), 1)
        self.assertEqual(len(root.findall(f".//{NS}g[@class='queue']")), 1)

    def test_a_boundary_holds_its_elements_and_says_what_it_is(self):
        svg = draw(CONTAINER, "light")
        root = ET.fromstring(svg)
        (border,) = root.findall(f".//{NS}g[@class='boundary']")
        l, t, r, b = rect_of(border.find(f"{NS}rect"))
        self.assertTrue(border.find(f"{NS}rect").get("stroke-dasharray"), "it is dashed")
        for inside in ("Web app", "Orders", "To ship"):
            x, y = where(svg, inside)
            self.assertTrue(l < x < r and t < y < b, inside)
        for outside in ("Buyer", "The bank"):
            x, y = where(svg, outside)
            self.assertFalse(l < x < r and t < y < b, outside)
        (label,) = root.findall(f".//{NS}g[@class='boundary-label']")
        self.assertEqual([e.text for e in label.iter(f"{NS}text")],
                         ["The shop", "[Software System]"])
        x, y = where(svg, "The shop")
        self.assertTrue(l < x < r and t < y < b, "the name sits in the box, at its top")

    def test_a_dynamic_diagram_numbers_its_arrows_in_order(self):
        found = words(draw(DYNAMIC, "light"))
        for text in ("1. Orders", "2. Saves it", "3. Asks for payment", "[SQL]"):
            self.assertIn(text, found)

    def test_a_deployment_node_is_a_box_in_three_dimensions_that_nests(self):
        svg = draw(DEPLOYMENT, "light")
        root = ET.fromstring(svg)
        nodes = root.findall(f".//{NS}g[@class='node']")
        self.assertEqual(len(nodes), 3, "two that hold others and one on its own")
        for n in nodes:
            self.assertEqual(len(n.findall(f"{NS}polygon")), 2, "a top face and a side face")
        found = words(svg)
        for text in ("«device»", "«execution environment»", "A server", "Docker", "The bank"):
            self.assertIn(text, found)
        boxes = [rect_of(n.find(f"{NS}rect")) for n in nodes]

        def named(name):
            x, y = where(svg, name)
            (found,) = [b for b in boxes if b[0] < x < b[2] and b[1] < y < b[1] + 24]
            return found

        outer, inner = named("A server"), named("Docker")
        self.assertTrue(outer[0] < inner[0] and inner[2] < outer[2] and outer[1] < inner[1]
                        and inner[3] < outer[3], "the execution environment sits in the device")
        x, y = where(svg, "Web app")
        self.assertTrue(inner[0] < x < inner[2] and inner[1] < y < inner[3])

    def test_every_box_is_colored_but_what_is_outside(self):
        neutral = THEMES["light"]["kinds"]["neutral"][0]
        for base in (CONTAINER, DEPLOYMENT):
            no_external = spec(base, elements=[e for e in base["elements"]
                                               if not e.get("external")],
                               relations=[r for r in base["relations"] if r["to"] != "bank"])
            root = ET.fromstring(draw(no_external, "light"))
            for g in root.iter(f"{NS}g"):
                if g.get("class") in ("boundary", "node"):
                    continue
                for shape in g:
                    with self.subTest(diagram=base["level"], shape=shape.tag):
                        self.assertNotEqual(shape.get("stroke"), neutral)
        root = ET.fromstring(draw(CONTEXT, "light"))
        strokes = [s.get("stroke") for g in root.iter(f"{NS}g") for s in g]
        self.assertIn(neutral, strokes, "an external system is gray")

    def test_light_and_dark_both_draw(self):
        light, dark = draw(CONTAINER, "light"), draw(CONTAINER, "dark")
        self.assertNotEqual(light, dark)
        self.assertIn("#ffffff", light)
        self.assertIn("#0d1117", dark)

    def test_a_bad_spec_says_what_is_wrong(self):
        els = CONTAINER["elements"]
        cases = [
            (spec(CONTAINER, level="code"), "level must be one of"),
            (spec(CONTEXT, elements=[*CONTEXT["elements"],
                                     {"id": "c", "type": "container", "name": "App",
                                      "col": 0, "row": 1}]),
             "a context diagram cannot hold a container"),
            (spec(DEPLOYMENT, elements=[*DEPLOYMENT["elements"],
                                        {"id": "p", "type": "person", "name": "You",
                                         "col": 2, "row": 0}]),
             "a deployment diagram cannot hold a person"),
            (spec(CONTAINER, elements=[*els[:1], dict(els[1], type="robot"), *els[2:]]),
             "type must be one of"),
            (spec(CONTAINER, elements=[*els[:1], dict(els[1], parent="mall"), *els[2:]]),
             "'mall', which is not a boundary"),
            (spec(CONTAINER, relations=[{"from": "buyer", "to": "nobody", "label": "x"}]),
             "nobody"),
            (spec(CONTAINER, elements=[*els[:1], dict(els[1], name=""), *els[2:]]), "name"),
            (spec(CONTEXT, elements=[*CONTEXT["elements"][:2],
                                     dict(CONTEXT["elements"][2], kind="ai")]),
             "external"),
            (spec(CONTAINER, elements=[*els[:4], dict(els[4], col=2)]),
             "'bank' sits in the box of boundary 'shop'"),
            (spec(CONTAINER, title=""), "title"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_wrong_type_gives_a_plain_error(self):
        els = CONTAINER["elements"]
        cases = [
            spec(CONTAINER, elements="buyer"),
            spec(CONTAINER, elements=["buyer"]),
            spec(CONTAINER, elements=[*els[:1], dict(els[1], name=7), *els[2:]]),
            spec(CONTAINER, elements=[*els[:1], dict(els[1], col="1"), *els[2:]]),
            spec(CONTAINER, elements=[*els[:1], dict(els[1], external="yes"), *els[2:]]),
            spec(CONTAINER, relations=["buyer -> web"]),
            spec(CONTAINER, relations=[{"from": "buyer", "to": "web", "label": 3}]),
            spec(CONTAINER, boundaries={"shop": "The shop"}),
            spec(CONTAINER, boundaries=[{"id": "shop", "name": ["The shop"]}]),
            spec(CONTAINER, level=4),
            spec(CONTAINER, names=["server"]),
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draw(bad, "light")

    def test_no_words_overlap_and_nothing_is_clipped(self):
        found = [(n, s) for n, s in (("context", CONTEXT), ("container", CONTAINER),
                                     ("dynamic", DYNAMIC), ("deployment", DEPLOYMENT))]
        found += [(name, json.loads((SRC / f"{name}.json").read_text())) for name in EXAMPLES]
        for name, s in found:
            for theme in ("light", "dark"):
                with self.subTest(diagram=name, theme=theme):
                    assert_clean(self, draw(s, theme))

    def test_the_examples_draw_tollgate(self):
        expect = {"c4-context": ("Tollgate", "You", "GitHub"),
                  "c4-container": ("The driver", "The gate", "The store", "The state folder"),
                  "c4-component": ("Component diagram for The driver",),
                  "c4-dynamic": ("1. Types the task", "8. Merges the change"),
                  "c4-deployment": ("Your machine", "«execution environment»")}
        for name, texts in expect.items():
            with self.subTest(diagram=name):
                found = words(draw(json.loads((SRC / f"{name}.json").read_text()), "light"))
                for text in texts:
                    self.assertIn(text, found)


def assert_clean(test, svg):
    """No two words overlap, no word or arrow leaves the picture, and no arrow's
    label sits on a box."""
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
        test.assertTrue(x0 <= l and r <= x0 + w and y0 <= t and b <= y0 + h, f"clipped: {text}")
        for l2, t2, r2, b2, other in boxes[a + 1:]:
            test.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, (text, other))
    for p in root.iter(f"{NS}path"):
        if p.get("class") in ("main", "side", "line"):
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", p.get("d"))]
            for x, y in zip(nums[::2], nums[1::2], strict=True):
                test.assertTrue(x0 <= x <= x0 + w and y0 <= y <= y0 + h, "an arrow is cut off")
    frames = [rect_of(r) for r in root.iter(f"{NS}rect") if r.get("class") == "label"]
    shapes = [rect_of(g.find(f"{NS}rect")) for g in root.iter(f"{NS}g")
              if g.get("class") in ("step", "person", "box") and g.find(f"{NS}rect") is not None]
    for i, f in enumerate(frames):
        for other in frames[i + 1:] + shapes:
            test.assertFalse(f[0] < other[2] and other[0] < f[2] and f[1] < other[3]
                             and other[1] < f[3], "a label on a box")


if __name__ == "__main__":
    unittest.main()
