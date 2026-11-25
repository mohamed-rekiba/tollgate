"""A diagram of any kind can put a small dot on every arrow: "packets": true."""

import json
import re
import unittest
from pathlib import Path

from diagram import draw

SRC = Path(__file__).resolve().parent.parent / "docs" / "diagrams" / "src"
# One docs diagram of each kind that has arrows.
KINDS = {"flow": "a-task", "c4": "c4-context", "sequence": "one-ticket-sequence",
         "state": "task-lifecycle", "usecase": "usecase"}


def spec(name: str, **extra) -> dict:
    return {**json.loads((SRC / f"{name}.json").read_text()), **extra}


def packets(svg: str) -> int:
    return len(re.findall(r'<circle class="packet"', svg))


class PacketsTest(unittest.TestCase):
    def test_no_packets_unless_the_spec_asks(self):
        for kind, name in KINDS.items():
            with self.subTest(kind=kind):
                base = {k: v for k, v in spec(name).items() if k != "packets"}
                self.assertEqual(packets(draw(base, "light")), 0)

    def test_every_kind_runs_a_dot_along_its_arrows_in_light_and_dark(self):
        for kind, name in KINDS.items():
            with self.subTest(kind=kind):
                light = draw(spec(name, packets=True), "light")
                dark = draw(spec(name, packets=True), "dark")
                self.assertGreater(packets(light), 0)
                self.assertEqual(packets(light), packets(dark))
                moving = re.findall(r'<circle class="packet"[^>]*><animateMotion', light)
                self.assertEqual(len(moving), packets(light))

    def test_a_dot_runs_over_and_over_on_a_path_of_the_arrow(self):
        svg = draw(spec("a-task", packets=True), "light")
        found = re.findall(r'<circle class="packet"[^>]*><animateMotion path="(M[^"]+)" '
                           r'dur="([0-9.]+)s" begin="(-[0-9.]+)s" repeatCount="indefinite"/>', svg)
        self.assertEqual(len(found), packets(svg))
        for path, dur, begin in found:
            with self.subTest(path=path[:30]):
                self.assertGreaterEqual(float(dur), 1.2)
                self.assertLess(float(begin[1:]), float(dur))

    def test_the_dots_do_not_move_in_step(self):
        svg = draw(spec("a-task", packets=True), "light")
        begins = re.findall(r'begin="(-[0-9.]+)s" repeatCount', svg)
        self.assertGreater(len(set(begins)), 1)

    def test_a_reader_who_asks_for_less_motion_sees_no_dots(self):
        for kind, name in KINDS.items():
            with self.subTest(kind=kind):
                style = re.search(r"<style>(.*?)</style>", draw(spec(name, packets=True), "light"),
                                  re.DOTALL).group(1)
                self.assertIn("prefers-reduced-motion", style)
                self.assertRegex(style, r"\.packet[^{]*\{display:none\}|\.packet,")

    def test_a_diagram_that_asks_for_no_dots_has_no_packet_style(self):
        plain = {k: v for k, v in spec("a-task").items() if k != "packets"}
        style = re.search(r"<style>(.*?)</style>", draw(plain, "light"), re.DOTALL).group(1)
        self.assertNotIn(".packet", style)

    def test_a_c4_diagram_keeps_its_dots_in_the_isometric_drawing(self):
        flat = spec("c4-container", packets=True)
        iso = {**flat, "style": "isometric"}
        self.assertGreater(packets(draw(flat, "light")), 0)
        self.assertGreater(packets(draw(iso, "light")), 0)

    def test_a_reply_runs_slower_than_a_request_in_a_sequence(self):
        svg = draw(spec("one-ticket-sequence", packets=True), "light")
        durations = {float(d) for d in re.findall(r'dur="([0-9.]+)s" begin', svg)}
        self.assertGreater(len(durations), 1)


if __name__ == "__main__":
    unittest.main()
