"""A scene can put a small dot on every lane, and color a lane by its kind."""

import unittest
import xml.etree.ElementTree as ET

from diagram import draw

NS = "{http://www.w3.org/2000/svg}"


def spec(**extra):
    base = {
        "type": "scene", "title": "T", "desc": "D", "size": [900, 600], "origin": [450, 300],
        "lanes": [
            {"path": [[0, 0], [100, 0]], "kind": "you"},
            {"path": [[0, 50], [100, 50]], "kind": "advisor", "side": True},
            {"path": [[0, 90], [100, 90]]},
            {"path": [[0, 130], [100, 130]], "kind": "you", "tone": "fail"},
        ],
        "ticket": {"legs": [{"path": [[0, 0], [100, 0]]}]},
    }
    return {**base, **extra}


class TestScenePackets(unittest.TestCase):
    def test_no_packets_unless_the_spec_asks(self):
        root = ET.fromstring(draw(spec(), "light"))
        self.assertEqual(root.findall(f".//{NS}circle[@class='packet']"), [])

    def test_a_packet_on_every_lane_runs_on_its_path_in_the_lane_color(self):
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                root = ET.fromstring(draw(spec(packets=True), theme))
                packets = root.findall(f".//{NS}circle[@class='packet']")
                lanes = root.findall(f".//{NS}polyline[@data-lane]")
                self.assertEqual(len(packets), 4)
                for packet, lane in zip(packets, lanes, strict=True):
                    self.assertEqual(packet.get("fill"), lane.get("stroke"))
                    motion = packet.find(f"{NS}animateMotion")
                    self.assertEqual(motion.get("repeatCount"), "indefinite")
                    self.assertTrue(motion.get("begin").startswith("-"))
                self.assertEqual(len(root.findall(f".//{NS}g[@class='ticket']")), 1)

    def test_the_ticket_is_drawn_over_the_packets(self):
        svg = draw(spec(packets=True), "light")
        self.assertGreater(svg.index('class="ticket"'), svg.rindex('class="packet"'))

    def test_packets_stop_for_readers_who_ask_for_less_motion(self):
        self.assertIn(".ticket,.packet,.moving-arm{display:none}", draw(spec(packets=True), "light"))
        self.assertNotIn(".packet", draw(spec(), "light"))

    def test_a_kind_colors_the_lane_and_its_arrowhead(self):
        root = ET.fromstring(draw(spec(), "light"))
        lanes = root.findall(f".//{NS}polyline[@data-lane]")
        self.assertEqual(lanes[0].get("marker-end"), "url(#arrow-you)")
        self.assertEqual(lanes[1].get("marker-end"), "url(#arrow-advisor)")
        self.assertEqual(lanes[2].get("marker-end"), "url(#arrow-main)")
        self.assertEqual(lanes[3].get("marker-end"), "url(#arrow-fail)")
        self.assertEqual(lanes[0].get("stroke"), "#0969da")
        ids = {m.get("id") for m in root.iter(f"{NS}marker")}
        self.assertTrue({"arrow-you", "arrow-advisor"} <= ids)
        self.assertNotIn("arrow-check", ids)

    def test_a_lane_with_no_kind_keeps_the_old_look(self):
        plain = spec()
        for lane in plain["lanes"]:
            lane.pop("kind", None)
        root = ET.fromstring(draw(plain, "light"))
        ids = {m.get("id") for m in root.iter(f"{NS}marker")}
        self.assertEqual(ids, {"arrow-main", "arrow-side", "arrow-fail", "arrow-pass"})

    def test_an_unknown_kind_is_refused(self):
        bad = spec()
        bad["lanes"][0]["kind"] = "purple"
        with self.assertRaisesRegex(ValueError, "lane kind"):
            draw(bad, "light")


if __name__ == "__main__":
    unittest.main()
