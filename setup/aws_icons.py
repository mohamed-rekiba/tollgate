"""Fetch the official AWS architecture icon package into the local cache.

    python3 -m setup.aws_icons                  # download it now (diagrams also do this on first use)
    python3 -m setup.aws_icons --zip FILE.zip   # use a package you downloaded yourself
    python3 -m setup.aws_icons --url URL        # a newer release

The package is AWS's, from https://aws.amazon.com/architecture/icons/. AWS
allows its icons in architecture diagrams. Tollgate keeps them out of git:
they live in the cache (TOLLGATE_AWS_ICONS, or ~/.cache/tollgate/aws-icons),
and a diagram copies in only the icons it uses.
"""

import argparse
import shutil
import sys
from pathlib import Path

from diagram.aws import CACHE, URL, fetch, unpack

__all__ = ["main", "unpack"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", help="a package zip you downloaded")
    parser.add_argument("--url", default=URL, help="the package link from the AWS page")
    parser.add_argument("--to", default=str(CACHE), help="where to keep the icons")
    args = parser.parse_args(argv)
    target = Path(args.to)
    if target.exists():
        shutil.rmtree(target)
    if args.zip:
        target.mkdir(parents=True)
        count = unpack(Path(args.zip).read_bytes(), target)
    else:
        count = fetch(args.url, target)
    print(f"{count} AWS icons in {target}")
    return 0 if count else 1


if __name__ == "__main__":
    sys.exit(main())
