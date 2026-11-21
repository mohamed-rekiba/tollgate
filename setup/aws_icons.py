"""Fetch the official AWS architecture icon package into a local cache.

    python3 -m setup.aws_icons                  # download the package named below
    python3 -m setup.aws_icons --zip FILE.zip   # use a package you downloaded yourself
    python3 -m setup.aws_icons --url URL        # a newer release

The package is AWS's, from https://aws.amazon.com/architecture/icons/. AWS
allows its icons in architecture diagrams. Tollgate keeps them out of git: they
live in the cache (TOLLGATE_AWS_ICONS, or ~/.cache/tollgate/aws-icons), and a
diagram copies in only the icons it uses. AWS releases a new package each
quarter; pass its link with --url.
"""

import argparse
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

from driver.aws import CACHE

URL = ("https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/"
       "architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip")


def unpack(data: bytes, target: Path) -> int:
    """Unpack the package, and any zip inside it. Return how many SVG files there are."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = Path(info.filename)
            if info.is_dir() or name.is_absolute() or ".." in name.parts or name.name.startswith("."):
                continue
            body = z.read(info)
            if name.suffix == ".zip":
                unpack(body, target / name.stem)
            elif name.suffix == ".svg":
                out = target / name
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(body)
    return sum(1 for _ in target.rglob("*.svg"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", help="a package zip you downloaded")
    parser.add_argument("--url", default=URL, help="the package link from the AWS page")
    parser.add_argument("--to", default=str(CACHE), help="where to keep the icons")
    args = parser.parse_args(argv)
    data = Path(args.zip).read_bytes() if args.zip else urllib.request.urlopen(args.url).read()
    target = Path(args.to)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    count = unpack(data, target)
    print(f"{count} AWS icons in {target}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
