"""Every diagram is an accessible SVG file, light and dark, drawn from its spec."""

import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "docs" / "diagrams"
NS = "{http://www.w3.org/2000/svg}"
SKIP = {".git", "node_modules", "dist", ".tollgate", "fixtures"}


def files(pattern):
    return [p for p in ROOT.rglob(pattern) if not SKIP & set(p.relative_to(ROOT).parts)]


def luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


class TestDiagrams(unittest.TestCase):
    def test_no_mermaid_in_markdown(self):
        found = [str(p.relative_to(ROOT)) for p in files("*.md")
                 if "```mermaid" in p.read_text(errors="ignore")]
        self.assertEqual(found, [], "draw these as SVG with the diagram skill")

    def test_every_svg_is_accessible_and_safe(self):
        svgs = files("*.svg")
        self.assertTrue(svgs)
        for path in svgs:
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_text()
                root = ET.fromstring(text)
                self.assertEqual(root.get("role"), "img")
                self.assertTrue(root.get("viewBox"))
                ids = (root.get("aria-labelledby") or "").split()
                self.assertEqual(len(ids), 2, "aria-labelledby names a title and a desc")
                title = root.find(f"{NS}title")
                desc = root.find(f"{NS}desc")
                self.assertIsNotNone(title)
                self.assertIsNotNone(desc)
                self.assertEqual([title.get("id"), desc.get("id")], ids)
                self.assertTrue((title.text or "").strip() and (desc.text or "").strip())
                self.assertTrue(root.findall(f".//{NS}text"), "use real text")
                for bad in ("script", "foreignObject", "image"):
                    self.assertFalse(root.findall(f".//{NS}{bad}"), bad)
                self.assertIsNone(re.search(r"\son[a-z]+\s*=", text), "event attribute")
                self.assertNotIn("prefers-color-scheme", text)
                self.assertIsNone(re.search(r"(href|src)=\"(https?:|//)", text), "external file")
                self.assertNotIn("@import", text)
                self.assertIsNone(re.search(r"url\(\s*['\"]?(https?:|//)", text), "external file")
                if "@keyframes" in text or "<animate" in text:
                    self.assertIn("prefers-reduced-motion", text, "motion must stop on request")

    def test_words_are_for_people(self):
        """No internal names in a picture: tag names, long hex ids, file paths."""
        for path in files("*.svg"):
            if "icons" in path.name:
                continue
            words = " ".join(e.text or "" for e in ET.fromstring(path.read_text()).iter()
                             if e.tag in (f"{NS}text",))
            with self.subTest(path=path.name):
                self.assertNotRegex(words, r"tg/|\b[0-9a-f]{12,}\b|\.py\b|\.ya?ml\b")

    def test_no_diagram_is_all_gray(self):
        """Gray is for what is outside the story. A diagram needs color that means something."""
        import json
        for spec in (DIAGRAMS / "src").glob("*.json"):
            data = json.loads(spec.read_text())
            if data.get("type") == "scene":
                continue
            kinds = {n.get("kind", "neutral") for n in data["nodes"] if not n.get("aws")}
            with self.subTest(diagram=spec.stem):
                self.assertNotEqual(kinds, {"neutral"}, "give the boxes the kind that drives them")

    def test_light_and_dark_twins(self):
        for path in DIAGRAMS.glob("*.svg"):
            twin = (path.with_name(path.stem[:-5] + ".svg") if path.stem.endswith("-dark")
                    else path.with_name(path.stem + "-dark.svg"))
            self.assertTrue(twin.exists(), f"{path.name} has no twin {twin.name}")

    def test_generator_output_is_current(self):
        result = subprocess.run([sys.executable, str(DIAGRAMS / "build.py"), "--check"],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_theme_colors_meet_contrast(self):
        sys.path.insert(0, str(DIAGRAMS))
        try:
            import build
        finally:
            sys.path.pop(0)
        for name, t in build.THEMES.items():
            fills = [t["box"]] + [tint for _, tint in t["kinds"].values()]
            for fill in fills:
                with self.subTest(theme=name, fill=fill):
                    self.assertGreaterEqual(contrast(t["text"], fill), 4.5)
                    self.assertGreaterEqual(contrast(t["sub"], fill), 4.5)
            for kind, (accent, tint) in t["kinds"].items():
                with self.subTest(theme=name, kind=kind):
                    self.assertGreaterEqual(contrast(accent, tint), 4.5)
            for tone, color in t["tones"].items():
                with self.subTest(theme=name, tone=tone):
                    self.assertGreaterEqual(contrast(color, t["page"]), 4.5)
            self.assertGreaterEqual(contrast(t["edge"], t["page"]), 3.0, name)
            self.assertGreaterEqual(contrast(t["sub"], t["page"]), 4.5, name)

    def test_every_diagram_is_used(self):
        markdown = "".join(p.read_text(errors="ignore") for p in files("*.md"))
        for spec in (DIAGRAMS / "src").glob("*.json"):
            with self.subTest(diagram=spec.stem):
                self.assertIn(f"{spec.stem}.svg", markdown)
                self.assertIn(f"{spec.stem}-dark.svg", markdown)


if __name__ == "__main__":
    unittest.main()
