"""The sequence diagram: participants, messages, bars, frames, and the moving dot,
drawn through diagram.draw."""

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram import draw

NS = "{http://www.w3.org/2000/svg}"


def spec(**extra):
    base = {
        "type": "sequence", "title": "A call", "desc": "The driver asks the gate.",
        "names": {"server": "Your machine"},
        "participants": [
            {"id": "d", "text": "The driver", "kind": "server", "icon": "workflow"},
            {"id": "b", "text": "Builder", "kind": "ai"},
            {"id": "g", "text": "The gate", "kind": "check", "icon": "gate"}],
        "messages": [
            {"from": "d", "to": "b", "text": "build it"},
            {"from": "b", "to": "d", "text": "the try", "reply": True},
            {"from": "d", "to": "d", "text": "run the checks", "note": "on your machine"},
            {"from": "d", "to": "g", "text": "judge it"},
            {"from": "g", "to": "d", "text": "it passes", "reply": True, "tone": "pass"},
            {"from": "g", "to": "d", "text": "it fails", "reply": True, "tone": "fail"}],
        "activations": [{"on": "d", "from": 0, "to": 5}, {"on": "g", "from": 3, "to": 5}],
        "frames": [{"kind": "loop", "from": 0, "to": 5, "label": "each try"},
                   {"kind": "alt", "from": 4, "to": 5,
                    "guards": [{"at": 4, "text": "tests pass"}, {"at": 5, "text": "else"}]}],
        "ticket": True}
    base.update(extra)
    return base


def root(s, theme="light"):
    return ET.fromstring(draw(s, theme))


def words(r):
    return [e.text for e in r.iter(f"{NS}text")]


def message(r, n):
    return r.find(f".//{NS}path[@data-n='{n}']")


def coords(d):
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(nums[0::2], nums[1::2], strict=False))


def lifeline_x(r, who):
    return float(r.find(f".//{NS}line[@data-of='{who}']").get("x1"))


def label_box(r, n):
    rect = r.find(f".//{NS}g[@class='label'][@data-n='{n}']/{NS}rect")
    x, y = float(rect.get("x")), float(rect.get("y"))
    return x, y, x + float(rect.get("width")), y + float(rect.get("height"))


def marker(r, url):
    name = re.match(r"url\(#(.+)\)", url).group(1)
    return r.find(f".//{NS}marker[@id='{name}']/{NS}path")


class SequenceTest(unittest.TestCase):
    def test_every_element_draws_with_its_words(self):
        r = root(spec())
        found = " ".join(words(r))
        for s in ("The driver", "Builder", "The gate", "YOUR MACHINE", "AI", "CHECK",
                  "build it", "the try", "run the checks", "on your machine", "judge it",
                  "it passes", "it fails", "loop", "each try", "alt", "[tests pass]", "[else]"):
            self.assertIn(s, found)
        self.assertEqual(len(r.findall(f".//{NS}line[@class='lifeline']")), 3)
        self.assertEqual(r.get("role"), "img")

    def test_a_reply_is_dashed_with_an_open_head_and_a_call_is_solid_and_filled(self):
        r = root(spec())
        call, reply = message(r, 0), message(r, 1)
        self.assertIn("call", call.get("class"))
        self.assertIsNone(call.get("stroke-dasharray"))
        self.assertNotEqual(marker(r, call.get("marker-end")).get("fill"), "none")
        self.assertIn("reply", reply.get("class"))
        self.assertTrue(reply.get("stroke-dasharray"))
        self.assertEqual(marker(r, reply.get("marker-end")).get("fill"), "none")

    def test_a_message_goes_from_one_lifeline_to_the_other(self):
        r = root(spec())
        pts = coords(message(r, 0).get("d"))
        x0, x1 = pts[0][0], pts[-1][0]
        self.assertAlmostEqual(x0, lifeline_x(r, "d"), delta=12)
        self.assertAlmostEqual(x1, lifeline_x(r, "b"), delta=12)

    def test_a_self_message_loops_back_to_the_same_lifeline(self):
        r = root(spec())
        pts = coords(message(r, 2).get("d"))
        x = lifeline_x(r, "d")
        self.assertAlmostEqual(pts[0][0], x, delta=12)
        self.assertAlmostEqual(pts[-1][0], x, delta=12)
        self.assertGreater(max(p[0] for p in pts), x + 20, "it goes out to the right")
        self.assertGreater(pts[-1][1], pts[0][1], "and comes back lower")

    def test_bars_sit_on_their_lifeline_over_their_messages(self):
        r = root(spec())
        (bar,) = r.findall(f".//{NS}rect[@data-on='g']")
        x, w = float(bar.get("x")), float(bar.get("width"))
        self.assertAlmostEqual(x + w / 2, lifeline_x(r, "g"), delta=1)
        top, bottom = float(bar.get("y")), float(bar.get("y")) + float(bar.get("height"))
        ys = [p[1] for n in (3, 4, 5) for p in coords(message(r, n).get("d"))]
        self.assertLess(top, min(ys))
        self.assertGreater(bottom, max(ys))
        self.assertGreater(top, max(p[1] for p in coords(message(r, 1).get("d"))),
                           "the bar starts after the messages before it")

    def test_frames_hold_their_messages_and_show_label_and_guards(self):
        r = root(spec())
        frames = {g.get("data-kind"): g for g in r.iter(f"{NS}g") if g.get("class") == "frame"}
        self.assertEqual(set(frames), {"loop", "alt"})
        for kind, rows in (("loop", range(6)), ("alt", (4, 5))):
            rect = frames[kind].find(f"{NS}rect")
            l, t = float(rect.get("x")), float(rect.get("y"))
            rr, b = l + float(rect.get("width")), t + float(rect.get("height"))
            for n in rows:
                for x, y in coords(message(r, n).get("d")):
                    self.assertTrue(l < x < rr and t < y < b, (kind, n))
                x0, y0, x1, y1 = label_box(r, n)
                self.assertTrue(l < x0 and x1 < rr and t < y0 and y1 < b, (kind, n))
        loop = frames["loop"].find(f"{NS}rect")
        alt = frames["alt"].find(f"{NS}rect")
        self.assertLess(float(loop.get("x")), float(alt.get("x")), "the loop holds the alt")
        self.assertIn("each try", words(frames["loop"]))
        self.assertIn("[tests pass]", words(frames["alt"]))
        self.assertIn("[else]", words(frames["alt"]))
        divider = frames["alt"].find(f"{NS}path[@class='divider']")
        y = coords(divider.get("d"))[0][1]
        self.assertLess(max(p[1] for p in coords(message(r, 4).get("d"))), y)
        self.assertLess(y, label_box(r, 5)[1], "the divider is above the else part")

    def test_labels_never_overlap(self):
        long = spec(messages=[
            {"from": "d", "to": "b", "text": "a very long label that needs a lot of room"},
            {"from": "b", "to": "b", "text": "another long label beside its loop"},
            {"from": "b", "to": "g", "text": "and one more long label to the gate"}],
            activations=[], frames=[])
        r = root(long)
        boxes = [label_box(r, n) for n in range(3)]
        lines = [lifeline_x(r, w) for w in ("d", "b", "g")]
        for x0, _, x1, _ in boxes:
            for x in lines:
                self.assertFalse(x0 < x < x1, "a label crosses a lifeline")
        vb = [float(v) for v in r.get("viewBox").split()]
        for x0, y0, x1, y1 in boxes:
            self.assertTrue(vb[0] < x0 and x1 < vb[0] + vb[2] and vb[1] < y0 and y1 < vb[1] + vb[3])

    def test_the_dot_follows_the_messages_in_order_and_stops_on_request(self):
        svg = draw(spec(), "light")
        r = ET.fromstring(svg)
        motion = r.find(f".//{NS}g[@class='ticket']/{NS}animateMotion")
        path = coords(motion.get("path"))
        at = 0
        for n in range(6):
            start = coords(message(r, n).get("d"))[0]
            found = [i for i, p in enumerate(path) if i >= at and abs(p[0] - start[0]) < 1
                     and abs(p[1] - start[1]) < 1]
            self.assertTrue(found, f"message {n} is on the path, after the one before")
            at = found[0]
        times = [float(v) for v in motion.get("keyTimes").split(";")]
        self.assertEqual(times, sorted(times))
        self.assertRegex(svg, r"prefers-reduced-motion:reduce\)\{[^}]*\}?\.ticket\{display:none")
        self.assertNotIn('class="ticket"', draw(spec(ticket=False), "light"))

    def test_light_and_dark_both_draw(self):
        light, dark = draw(spec(), "light"), draw(spec(), "dark")
        self.assertNotEqual(light, dark)
        for svg in (light, dark):
            r = ET.fromstring(svg)
            self.assertEqual(r.get("aria-labelledby"), "title desc")
            self.assertFalse(r.findall(f".//{NS}script"))

    def test_a_bad_spec_says_what_is_wrong(self):
        good = spec()
        cases = [
            ({"participants": []}, "no participants"),
            ({"messages": [{"from": "d", "to": "x", "text": "hi"}]}, "not a participant"),
            ({"participants": [dict(good["participants"][0], kind="robot")]}, "kind must be"),
            ({"participants": [dict(good["participants"][0], icon="rocket")]}, "no icon named"),
            ({"frames": [{"kind": "loop", "from": 2, "to": 9}]}, "numbered 0 to 5"),
            ({"frames": [{"kind": "par", "from": 0, "to": 1}]}, "kind must be one of"),
            ({"frames": [{"kind": "loop", "from": 0, "to": 3},
                         {"kind": "opt", "from": 2, "to": 5}]}, "cross"),
            ({"activations": [{"on": "x", "from": 0, "to": 1}]}, "not a participant"),
            ({"messages": [{"from": "d", "to": "b", "text": "hi", "tone": "ok"}],
              "activations": [], "frames": []}, "tone"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(dict(good, **bad), "light")
            self.assertIn(says, str(err.exception))

    def test_a_wrong_type_is_a_plain_error(self):
        good = spec()
        p0, m0 = good["participants"][0], good["messages"][0]
        cases = [
            ({"participants": ["d"]}, "participant 0 must be an object"),
            ({"participants": {"d": "x"}}, "'participants' must be a list"),
            ({"participants": [dict(p0, text=5)]}, "'text' must be words"),
            ({"names": ["server"]}, "'names' must be an object"),
            ({"messages": [dict(m0, text=7)]}, "'text' must be words"),
            ({"messages": ["d to b"]}, "message 0 must be an object"),
            ({"activations": [{"on": "d", "from": "0", "to": 1}]}, "a whole number"),
            ({"frames": [{"kind": "loop", "from": 0, "to": 1, "label": 3}]}, "'label' must be"),
            ({"frames": [{"kind": "opt", "from": 0, "to": 1, "guards": ["ok"]}]},
             "guard 0 must be an object"),
            ({"frames": [{"kind": "opt", "from": 0, "to": 1,
                          "guards": [{"at": 0, "text": 1}]}]}, "'text' must be words"),
            ({"frames": [{"kind": "loop", "from": 0.5, "to": 1}]}, "a whole number"),
            ({"ticket": "yes"}, "'ticket' must be true or false"),
        ]
        for bad, says in cases:
            with self.subTest(says=says), self.assertRaises(ValueError) as err:
                draw(dict(good, **bad), "light")
            self.assertIn(says, str(err.exception))

    def test_the_example_draws_in_both_themes(self):
        path = Path(__file__).resolve().parent.parent / "docs/diagrams/src/one-ticket-sequence.json"
        example = json.loads(path.read_text())
        for theme in ("light", "dark"):
            r = root(example, theme)
            self.assertEqual(len(r.findall(f".//{NS}path[@class='message call']"))
                             + len(r.findall(f".//{NS}path[@class='message reply']")),
                             len(example["messages"]))
            self.assertIn("The gate", words(r))


if __name__ == "__main__":
    unittest.main()
