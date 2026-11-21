"""AWS architecture icons, read from a local copy of the official icon package.

AWS allows its icons in architecture diagrams, unchanged. Tollgate does not
ship them. The first diagram that needs one downloads the official package
from AWS into a cache on your machine (TOLLGATE_AWS_ICONS, or
~/.cache/tollgate/aws-icons), once. Set TOLLGATE_AWS_ICONS_FETCH=0 to stop
that; then run `python3 -m setup.aws_icons --zip <file>` with a package you
downloaded yourself.
A diagram then copies each icon it needs into its own SVG, unchanged except
that the icon's internal ids get a prefix, so two icons in one file do not
clash.

    from diagram import aws
    aws.service("s3")       # the SVG text of the Amazon S3 icon
    aws.group("vpc")        # (the SVG text of the VPC group icon, its color, dashed?)
"""

import io
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from functools import cache
from pathlib import Path

CACHE = Path(os.environ.get("TOLLGATE_AWS_ICONS", Path.home() / ".cache" / "tollgate" / "aws-icons"))

# Short names people type, to words in the official file names.
ALIASES = {
    "s3": "simple storage service", "ec2": "ec2", "lambda": "lambda", "rds": "rds",
    "dynamodb": "dynamodb", "sqs": "simple queue service", "sns": "simple notification service",
    "cloudfront": "cloudfront", "route53": "route 53", "api gateway": "api gateway",
    "apigw": "api gateway", "ecs": "elastic container service", "eks": "elastic kubernetes service",
    "ecr": "elastic container registry", "iam": "identity and access management",
    "kms": "key management service", "secrets manager": "secrets manager",
    "cloudwatch": "cloudwatch", "elb": "elastic load balancing", "alb": "elastic load balancing",
    "vpc": "virtual private cloud", "efs": "efs", "step functions": "step functions",
    "eventbridge": "eventbridge", "cognito": "cognito", "waf": "waf", "bedrock": "bedrock",
}

# The groups and how AWS draws their border. The color comes from the group's
# own icon in the package; only the line style is set here.
GROUPS = {
    "cloud": ("cloud logo", False), "account": ("account", False),
    "region": ("region", True), "az": ("availability zone", True),
    "vpc": ("virtual private cloud vpc", False), "public subnet": ("public subnet", False),
    "private subnet": ("private subnet", False), "security group": ("security group", True),
    "auto scaling": ("auto scaling group", True), "data center": ("corporate data center", False),
}


# The newest package on https://aws.amazon.com/architecture/icons/ (AWS releases
# one each quarter). Update this link when AWS releases a new one.
URL = ("https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/"
       "architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip")


class Missing(LookupError):
    pass


# Limits on the package, so a broken or hostile file cannot fill the disk.
MAX_BYTES, MAX_FILES, MAX_DEPTH = 300 * 2**20, 20000, 2


def unpack(data: bytes, target: Path, depth: int = 0) -> int:
    """Unpack the package's SVG files, and any zip one level inside it.

    Return how many SVG files there are. Raise ValueError on a package over the limits.
    """
    if depth > MAX_DEPTH:
        raise ValueError("the AWS package nests zips too deep")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
            raise ValueError("the AWS package is larger than expected")
        for info in infos:
            name = Path(info.filename)
            if info.is_dir() or name.is_absolute() or ".." in name.parts or name.name.startswith("."):
                continue
            if name.suffix == ".zip":
                unpack(z.read(info), target / name.stem, depth + 1)
            elif name.suffix == ".svg":
                out = target / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(info))
    return sum(1 for _ in target.rglob("*.svg"))


def fetch(url: str = URL, target: Path | None = None) -> int:
    """Download the official package from AWS into the cache. Return the icon count.

    It unpacks into a new folder first and moves it into place only when that
    worked, so a failed download leaves no half-filled cache behind.
    """
    target = Path(target or CACHE)
    if not url.startswith("https://d1.awsstatic.com/"):
        raise ValueError("the AWS package must come from https://d1.awsstatic.com/")
    print(f"Downloading the AWS icon package once, into {target} ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as reply:
        # A redirect must stay on AWS's host, and the body must stay under the limit.
        if not reply.geturl().startswith("https://d1.awsstatic.com/"):
            raise ValueError("the AWS package redirected away from AWS's host")
        data = reply.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("the AWS package is larger than expected")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".aws-icons-", dir=target.parent))
    try:
        count = unpack(data, stage)
        if not count:
            raise ValueError("the AWS package holds no SVG icons")
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return count


# The SVG parts an icon may use. Anything else is dropped when an icon is copied
# into a diagram, so a broken or tampered icon cannot bring a script, an event
# handler, or an outside file into a committed picture.
SAFE_TAGS = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
             "defs", "lineargradient", "radialgradient", "stop", "clippath", "mask", "title",
             "desc", "use", "symbol", "text", "tspan"}
SAFE_ATTRS = {"id", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "width",
              "height", "points", "viewbox", "fill", "fill-rule", "fill-opacity", "stroke",
              "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit",
              "stroke-opacity", "stroke-dasharray", "opacity", "transform", "offset",
              "stop-color", "stop-opacity", "gradientunits", "gradienttransform", "clip-path",
              "clip-rule", "mask", "href", "preserveaspectratio", "class", "style",
              "font-size", "font-family", "font-weight", "text-anchor", "version"}


def clean(svg: str) -> str:
    """Keep only the safe SVG parts of an icon."""
    ns = "http://www.w3.org/2000/svg"
    ET.register_namespace("", ns)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(svg)

    def local(name):
        return name.split("}", 1)[-1].lower()

    def scrub(el):
        for child in list(el):
            if local(child.tag) not in SAFE_TAGS:
                child.tail = None
                el.remove(child)
            else:
                scrub(child)
        for key in list(el.attrib):
            name, value = local(key), el.attrib[key]
            urls = re.findall(r"url\(\s*['\"]?([^)'\"\s]*)", value)
            unsafe_url = any(not u.startswith("#") for u in urls)
            if (name not in SAFE_ATTRS or name.startswith("on") or unsafe_url
                    or (name == "href" and not value.startswith("#"))
                    or (name == "style" and re.search(r"url\(\s*['\"]?[^#'\"\s]|@import|expression",
                                                      value, re.IGNORECASE))):
                del el.attrib[key]

    if local(root.tag) != "svg":
        raise Missing("an AWS icon file is not an SVG")
    scrub(root)
    return ET.tostring(root, encoding="unicode")


def _words(name: str) -> str:
    name = re.sub(r"^(Arch|Res)_|_(16|32|48|64)(_Dark)?$", "", Path(name).stem)
    name = re.sub(r"^(Amazon|AWS)[-_ ]", "", name)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


@cache
def index(root: str) -> dict:
    """Every SVG of the package by kind ('service', 'resource', 'group') and words."""
    base = Path(root)
    if not base.exists() and root == str(CACHE) and os.environ.get("TOLLGATE_AWS_ICONS_FETCH") != "0":
        try:
            fetch()
        except (OSError, ValueError, zipfile.BadZipFile) as err:
            raise Missing(f"Could not download the AWS icons ({err}). Download the package from "
                          f"https://aws.amazon.com/architecture/icons/ and run: "
                          f"python3 -m setup.aws_icons --zip <file>") from err
    if not base.exists():
        raise Missing(f"No AWS icons at {base}. Run: python3 -m setup.aws_icons")
    out = {"service": {}, "resource": {}, "group": {}}
    for path in base.rglob("*.svg"):
        text = str(path).lower()
        if "dark" in path.stem.lower():
            continue
        kind = ("group" if "group" in text else "service" if "/arch_" in text or "service" in text
                else "resource")
        size = re.search(r"_(16|32|48|64)\.svg$", path.name)
        best = {"service": "48", "resource": "48", "group": "32"}[kind]
        key = _words(path.name)
        old = out[kind].get(key)
        if old is None or (size and size.group(1) == best):
            out[kind][key] = path
    return out


def _find(kind: str, name: str, root: str | None) -> Path:
    table = index(str(root or CACHE))[kind]
    want = ALIASES.get(name.lower(), name.lower())
    want = " ".join(re.sub(r"[^a-z0-9]+", " ", want).split())
    if want in table:
        return table[want]
    hits = sorted((k for k in table if want in k), key=len)
    if not hits:
        raise Missing(f"No AWS {kind} icon matches '{name}'.")
    return table[hits[0]]


def _inline(path: Path, prefix: str) -> str:
    """The icon's SVG, without the XML header, its ids prefixed."""
    text = path.read_text()
    text = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", text, flags=re.DOTALL).strip()
    text = clean(text)
    ids = set(re.findall(r'\bid="([^"]+)"', text))
    for old in sorted(ids, key=len, reverse=True):
        new = f"{prefix}-{re.sub(r'[^A-Za-z0-9_-]', '-', old)}"
        text = text.replace(f'id="{old}"', f'id="{new}"')
        text = text.replace(f"url(#{old})", f"url(#{new})")
        text = text.replace(f'href="#{old}"', f'href="#{new}"')
    return text


def service(name: str, prefix: str = "aws", root: str | None = None) -> str:
    try:
        return _inline(_find("service", name, root), prefix)
    except Missing:
        return _inline(_find("resource", name, root), prefix)


def group(name: str, prefix: str = "awsg", root: str | None = None) -> tuple:
    """(icon SVG, border color, dashed) for one of GROUPS."""
    words, dashed = GROUPS[name]
    path = _find("group", words, root)
    text = path.read_text()
    colors = re.findall(r'fill[:=]\s*"?(#[0-9A-Fa-f]{6})', text)
    color = next((c for c in colors if c.lower() not in ("#ffffff", "#fff")), "#232f3e")
    return _inline(path, prefix), color, dashed


def place(svg: str, x: float, y: float, size: float) -> str:
    """Put an inlined icon at x, y and size, keeping its own drawing as it is."""
    head, rest = svg.split(">", 1)
    head = re.sub(r'\s(width|height|x|y)="[^"]*"', "", head)
    head = head.replace("<svg", f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}"', 1)
    return head + ">" + rest
