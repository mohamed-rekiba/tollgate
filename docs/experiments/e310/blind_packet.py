"""Build the blind review packet: each ticket's two changes as A and B.

    python3 docs/experiments/e310/blind_packet.py --repo . --pairs pairs.json --out packet/

pairs.json: [{"ticket": "...", "tollgate": <sha>, "plain": <sha>}, ...]. For each
ticket it writes <ticket>-A.diff and <ticket>-B.diff, with the order picked at
random, and key.json, which says which is which. Give the reviewer the diffs only,
not key.json. The reviewer marks each diff merge or not in 15 minutes.
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    key = {}
    for pair in json.loads(Path(args.pairs).read_text()):
        arms = [("tollgate", pair["tollgate"]), ("plain", pair["plain"])]
        random.shuffle(arms)
        for label, (arm, sha) in zip("AB", arms, strict=True):
            base = subprocess.run(["git", "merge-base", args.base, sha], cwd=args.repo,
                                  capture_output=True, text=True, check=True).stdout.strip()
            diff = subprocess.run(["git", "diff", base, sha, "--", ".", ":(exclude).tollgate"],
                                  cwd=args.repo, capture_output=True, text=True, check=True).stdout
            (out / f"{pair['ticket']}-{label}.diff").write_text(diff)
            key[f"{pair['ticket']}-{label}"] = arm
    (out / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    print(f"wrote {len(key)} diffs and key.json to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
