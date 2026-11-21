"""The review's findings on the diagram package, each held by a test."""

import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from diagram import aws, draw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docs" / "diagrams"))
import build

HOSTILE = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           'onload="alert(1)" viewBox="0 0 48 48"><script>alert(2)</script>'
           '<foreignObject><div>x</div></foreignObject>'
           '<rect width="48" height="48" fill="#ED7100" onclick="x()"/>'
           '<use href="https://evil.example/x.svg#a"/><use href="#ok"/>'
           '<path d="M0 0" style="fill:url(https://evil.example/a)"/>'
           '<image href="https://evil.example/p.png"/></svg>')


def zip_of(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return out.getvalue()


class CleanTest(unittest.TestCase):
    def test_a_tampered_icon_loses_everything_unsafe(self):
        text = aws.clean(HOSTILE)
        for bad in ("script", "onload", "onclick", "foreignObject", "evil.example", "<image"):
            self.assertNotIn(bad, text)
        self.assertIn('href="#ok"', text)
        self.assertIn("#ED7100", text)

    def test_the_cleaned_icon_reaches_the_diagram(self):
        with tempfile.TemporaryDirectory() as d:
            icon = Path(d, "Architecture-Service-Icons_1/Arch_Compute/48/Arch_AWS-Lambda_48.svg")
            icon.parent.mkdir(parents=True)
            icon.write_text(HOSTILE)
            aws.index.cache_clear()
            with mock.patch.object(aws, "CACHE", Path(d)):
                svg = draw({"title": "t", "desc": "d", "edges": [],
                            "nodes": [{"id": "f", "text": "Lambda", "col": 0, "row": 0,
                                       "aws": "lambda"}]}, "light")
            aws.index.cache_clear()
        self.assertNotIn("<script", svg)
        self.assertNotIn("evil.example", svg)


class DownloadTest(unittest.TestCase):
    def test_only_aws_own_host(self):
        with self.assertRaises(ValueError):
            aws.fetch("https://evil.example/pack.zip", Path(tempfile.mkdtemp(), "x"))

    def test_limits_on_size_and_nesting(self):
        with mock.patch.object(aws, "MAX_FILES", 2), tempfile.TemporaryDirectory() as d, \
                self.assertRaises(ValueError):
            aws.unpack(zip_of({f"a{i}.svg": "<svg/>" for i in range(3)}), Path(d))
        deep = zip_of({"a.svg": "<svg/>"})
        for _ in range(4):
            deep = zip_of({"inner.zip": deep})
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            aws.unpack(deep, Path(d))

    def test_a_broken_download_leaves_no_cache_behind(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d, "icons")
            reply = mock.Mock()
            reply.read.return_value = b"this is not a zip"
            with mock.patch("urllib.request.urlopen", return_value=reply), \
                    self.assertRaises(zipfile.BadZipFile):
                aws.fetch(aws.URL, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(d).iterdir()), [])


class WorkflowReaderTest(unittest.TestCase):
    def test_block_list_needs(self):
        text = ("on: push\njobs:\n  a:\n    runs-on: x\n  b:\n    runs-on: x\n  c:\n"
                "    needs:\n      - a\n      - b\n    runs-on: x\n")
        jobs = {j["name"]: j["needs"] for j in build.workflow_jobs(text)}
        self.assertEqual(jobs["c"], ["a", "b"])

    def test_no_jobs_says_so(self):
        with self.assertRaises(ValueError) as err:
            build.workflow_jobs("on: push\n")
        self.assertIn("jobs", str(err.exception))


class SpecCheckTest(unittest.TestCase):
    def spec(self, **kw):
        base = {"title": "t", "desc": "d", "edges": [],
                "nodes": [{"id": "a", "text": "A", "col": 0, "row": 0}]}
        base.update(kw)
        return base

    def test_plain_messages(self):
        cases = [(self.spec(nodes=[]), "no nodes"),
                 (self.spec(edges=[{"from": "a", "to": "z"}]), "'z', which is not a node"),
                 (self.spec(edges=[{"from": "a", "to": "a", "tone": "x)"}]), "tone"),
                 (self.spec(nodes=[{"id": "a", "text": "A", "col": 0, "row": 0, "kind": "x"}]),
                  "kind must be"),
                 (self.spec(ticket={"path": []}), "empty path")]
        for spec, words in cases:
            with self.subTest(words=words), self.assertRaises(ValueError) as err:
                draw(spec, "light")
            self.assertIn(words, str(err.exception))

    def test_a_scene_ticket_needs_legs(self):
        with self.assertRaises(ValueError):
            draw({"type": "scene", "title": "t", "desc": "d", "ticket": {"legs": []}}, "light")


if __name__ == "__main__":
    unittest.main()
