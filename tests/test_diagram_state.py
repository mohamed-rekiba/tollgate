"""The state machine kind: states, the initial dot and the final ring, labeled
transitions, self-transitions, one level of nested states, and the moving dot."""

import copy
import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram import draw
from diagram.flow import text_width

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src" / "task-lifecycle.json"

NS = "{http://www.w3.org/2000/svg}"


def words(svg):
    return " ".join(e.text or "" for e in ET.fromstring(svg).iter(f"{NS}text"))


def numbers(d):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]


def state_box(svg, sid):
    """The outline of a state as (left, top, right, bottom)."""
    group = ET.fromstring(svg).find(f".//{NS}g[@data-state='{sid}']")
    rect = group.find(f"{NS}rect")
    x, y = float(rect.get("x")), float(rect.get("y"))
    return x, y, x + float(rect.get("width")), y + float(rect.get("height"))


def arrows(svg):
    return [numbers(p.get("d")) for p in ET.fromstring(svg).iter(f"{NS}path")
            if p.get("class") == "transition"]


SPEC = {
    "type": "state", "title": "A door", "desc": "A door opens and shuts, and locks.",
    "names": {"server": "The house"},
    "states": [
        {"id": "start", "initial": True, "col": 0, "row": 0},
        {"id": "shut", "text": "Shut\nNobody walks through", "col": 1, "row": 0, "kind": "you"},
        {"id": "open", "text": "Open\nPeople walk through", "col": 2, "row": 0, "kind": "ai",
         "icon": "home"},
        {"id": "locked", "text": "Locked\nOnly a key opens it", "col": 1, "row": 1,
         "kind": "server"},
        {"id": "gone", "final": True, "col": 3, "row": 0},
    ],
    "transitions": [
        {"from": "start", "to": "shut"},
        {"from": "shut", "to": "open", "event": "push", "guard": "not locked", "tone": "pass"},
        {"from": "open", "to": "open", "event": "wind", "guard": "it stays open"},
        {"from": "shut", "to": "locked", "event": "turn the key"},
        {"from": "open", "to": "gone", "event": "taken down", "tone": "fail"},
    ],
    "ticket": {"path": [["start", "shut"], ["shut", "open"], ["open", "gone"]]},
}

NESTED = {
    "type": "state", "title": "Nested", "desc": "A state with two states inside it.",
    "states": [
        {"id": "start", "initial": True, "col": 0, "row": 0},
        {"id": "work", "text": "Working\nTwo steps inside", "col": 1, "row": 0, "kind": "ai"},
        {"id": "inner_start", "initial": True, "col": 0, "row": 0, "parent": "work"},
        {"id": "first", "text": "First step", "col": 1, "row": 0, "kind": "ai", "parent": "work"},
        {"id": "second", "text": "Second step", "col": 2, "row": 0, "kind": "check",
         "parent": "work"},
        {"id": "after", "text": "After\nOutside the box", "col": 1, "row": 1, "kind": "you"},
        {"id": "end", "final": True, "col": 2, "row": 1},
    ],
    "transitions": [
        {"from": "start", "to": "work"},
        {"from": "inner_start", "to": "first"},
        {"from": "first", "to": "second", "event": "done"},
        {"from": "second", "to": "after", "event": "leave early"},
        {"from": "work", "to": "after", "event": "all done", "route": "vh"},
        {"from": "after", "to": "end"},
    ],
}


def spec(**change):
    out = copy.deepcopy(SPEC)
    out.update(change)
    return out


class StateTest(unittest.TestCase):
    def test_every_state_draws_with_its_words(self):
        svg = draw(SPEC, "light")
        for text in ("Shut", "Nobody walks through", "Open", "People walk through", "Locked",
                     "Only a key opens it", "YOU", "AI", "THE HOUSE"):
            self.assertIn(text, words(svg))
        root = ET.fromstring(svg)
        self.assertEqual(root.get("role"), "img")
        self.assertTrue(root.get("viewBox"))
        self.assertEqual(root.find(f"{NS}title").text, "A door")

    def test_one_filled_initial_dot_and_a_final_ring_with_a_dot(self):
        root = ET.fromstring(draw(SPEC, "light"))
        starts = root.findall(f".//{NS}g[@class='initial']")
        self.assertEqual(len(starts), 1)
        (dot,) = starts[0].findall(f"{NS}circle")
        self.assertNotEqual(dot.get("fill"), "none")
        (end,) = root.findall(f".//{NS}g[@class='final']")
        ring, inner = end.findall(f"{NS}circle")
        self.assertTrue(ring.get("stroke"), "the outer circle is a ring")
        self.assertLess(float(inner.get("r")), float(ring.get("r")))
        self.assertEqual(inner.get("fill"), ring.get("stroke"), "a filled dot inside")

    def test_a_label_shows_the_event_and_the_guard(self):
        self.assertIn("push [not locked]", words(draw(SPEC, "light")))
        self.assertIn("turn the key", words(draw(SPEC, "light")))

    def test_a_self_transition_loops_back_to_the_same_state(self):
        svg = draw(SPEC, "light")
        left, top, right, _ = state_box(svg, "open")
        loops = [d for d in arrows(svg) if d[1] == top and d[-1] == top]
        self.assertEqual(len(loops), 1, "one arrow leaves the top and comes back to it")
        d = loops[0]
        self.assertTrue(left < d[0] < right and left < d[-2] < right)
        self.assertLess(min(d[1::2]), top, "it reaches out above the state")
        self.assertIn("wind [it stays open]", words(svg))

    def test_children_sit_inside_the_parent_and_a_transition_leaves_it(self):
        svg = draw(NESTED, "dark")
        outer = state_box(svg, "work")
        for child in ("first", "second"):
            l, t, r, b = state_box(svg, child)
            self.assertTrue(outer[0] < l and r < outer[2] and outer[1] < t and b < outer[3], child)
        after = state_box(svg, "after")
        self.assertGreater(after[1], outer[3], "the state outside is below the box")
        ends = [d[-2:] for d in arrows(svg)]
        self.assertTrue(any(y == after[1] for _, y in ends), "an arrow reaches the outside state")
        second = state_box(svg, "second")
        leaving = [d for d in arrows(svg) if second[0] <= d[0] <= second[2] and d[1] == second[3]
                   and d[-1] == after[1]]
        self.assertEqual(len(leaving), 1, "a child's transition crosses the parent's border")
        self.assertEqual(len(ET.fromstring(svg).findall(f".//{NS}g[@class='initial']")), 2,
                         "the parent has its own initial dot")

    def test_the_dot_follows_the_path_and_stops_on_request(self):
        svg = draw(SPEC, "light")
        motion = ET.fromstring(svg).find(f".//{NS}g[@class='ticket']/{NS}animateMotion")
        path = numbers(motion.get("path"))
        shut, opened = state_box(svg, "shut"), state_box(svg, "open")
        self.assertIn(shut[0], path, "it reaches the first state")
        self.assertIn(opened[0], path, "then the second")
        self.assertRegex(svg, r"prefers-reduced-motion:reduce\)\{.*\.ticket\{display:none")
        self.assertIn(ET.fromstring(svg).find(f".//{NS}g[@class='ticket']//{NS}animate")
                      .get("values").split(";")[1], svg, "it takes the arrow's tone")

    def test_light_and_dark_both_draw(self):
        light, dark = draw(SPEC, "light"), draw(SPEC, "dark")
        self.assertNotEqual(light, dark)
        self.assertIn("#ffffff", light)
        self.assertIn("#0d1117", dark)

    def test_a_bad_spec_says_what_is_wrong(self):
        states = SPEC["states"]
        cases = [
            (spec(transitions=[{"from": "shut", "to": "nowhere"}]), "nowhere"),
            (spec(states=[*states[:1], dict(states[1], kind="robot"), *states[2:]]), "kind"),
            (spec(states=[*states[:1], dict(states[1], icon="rocket"), *states[2:]]), "rocket"),
            (spec(states=[*states, {"id": "again", "initial": True, "col": 0, "row": 1}]),
             "two initial states"),
            (spec(states=[*states, {"id": "deep", "text": "Deep", "col": 0, "row": 0,
                                    "parent": "nested"},
                          {"id": "nested", "text": "Nested", "col": 0, "row": 0,
                           "parent": "locked"}]), "one level"),
            (spec(ticket={"path": [["shut", "gone"]]}), "not drawn"),
            (spec(title=""), "title"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(bad, "light")
            self.assertIn(says, str(err.exception))

    def test_a_wrong_type_gives_a_plain_error(self):
        states = SPEC["states"]
        cases = [
            spec(states=["shut"]),
            spec(states=[*states[:1], dict(states[1], text=7), *states[2:]]),
            spec(states=[*states[:1], dict(states[1], col="1"), *states[2:]]),
            spec(states=[*states[:1], dict(states[1], row=1.5), *states[2:]]),
            spec(transitions=["shut -> open"]),
            spec(transitions=[{"from": "shut", "to": "open", "event": 3}]),
            spec(transitions=[{"from": "shut", "to": "open", "guard": ["a"]}]),
            spec(ticket=True),
            spec(ticket={"path": "shut, open"}),
            spec(names=["server"]),
            spec(title=5),
        ]
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draw(bad, "light")

    def test_transitions_are_solid_and_only_the_dot_moves(self):
        root = ET.fromstring(draw(SPEC, "light"))
        lines = [p for p in root.iter(f"{NS}path") if p.get("class") == "transition"]
        self.assertTrue(lines)
        for line in lines:
            self.assertIsNone(line.get("stroke-dasharray"))
        self.assertFalse([p for p in root.iter(f"{NS}path") if p.get("class") in ("main", "side")])

    def test_no_words_overlap_and_nothing_is_clipped(self):
        for name, found in (("door", SPEC), ("nested", NESTED),
                            ("task", json.loads(EXAMPLE.read_text()))):
            for theme in ("light", "dark"):
                with self.subTest(diagram=name, theme=theme):
                    self.assert_clean(draw(found, theme))

    def assert_clean(self, svg):
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
            self.assertTrue(x0 <= l and r <= x0 + w and y0 <= t and b <= y0 + h, text)
            for l2, t2, r2, b2, other in boxes[a + 1:]:
                self.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, (text, other))
        # Labels sit apart from each other and from the states.
        frames = [r for r in root.iter(f"{NS}rect") if r.get("rx") == "3"]
        states = [r for r in root.iter(f"{NS}rect") if r.get("rx") == "12"]

        def edges(r):
            x, y = float(r.get("x")), float(r.get("y"))
            return x, y, x + float(r.get("width")), y + float(r.get("height"))

        for i, f in enumerate(frames):
            l, t, r, b = edges(f)
            for other in frames[i + 1:] + states:
                l2, t2, r2, b2 = edges(other)
                self.assertFalse(l < r2 and l2 < r and t < b2 and t2 < b, "a label on a box")
        for d in arrows(svg):
            for x, y in zip(d[::2], d[1::2], strict=True):
                self.assertTrue(x0 <= x <= x0 + w and y0 <= y <= y0 + h, "an arrow is cut off")

    def test_the_task_lifecycle_example_draws(self):
        svg = draw(json.loads(EXAMPLE.read_text()), "light")
        for text in ("Analyzing", "Building the tickets", "At the gate", "A ready change"):
            self.assertIn(text, words(svg))


if __name__ == "__main__":
    unittest.main()
