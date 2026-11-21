"""List every question that waits for a person, across the projects of a home.

A question is an open issue with the label tg-waiting. Run it in a home, or name
repositories with --repo.
"""

import argparse
import json
import sys

from setup.gh import Gh, GhError
from setup.home import load


def inbox(repos: list, gh=None) -> list:
    gh = gh or Gh()
    out = []
    for repo in repos:
        try:
            issues = gh.get(f"repos/{repo}/issues?state=open&labels=tg-waiting&per_page=100")
        except GhError as err:
            out.append({"repo": repo, "issue": None, "title": f"could not read: {err}"})
            continue
        for issue in issues or []:
            out.append({"repo": repo, "issue": issue["number"], "title": issue["title"],
                        "url": issue.get("html_url", "")})
    return out


def main(argv=None, gh=None) -> int:
    parser = argparse.ArgumentParser(prog="inbox", description=__doc__)
    parser.add_argument("--home", default=".")
    parser.add_argument("--repo", action="append", help="owner/name; repeat for more")
    parser.add_argument("--json", action="store_true", help="print the questions as a JSON list")
    args = parser.parse_args(argv)
    repos = args.repo or [p["name"] for p in load(args.home)["projects"]]
    found = inbox(repos, gh)
    if args.json:
        print(json.dumps(found))
        return 0
    if not found:
        print("Nothing waits for a person.")
    for item in found:
        print(f"{item['repo']}#{item['issue']}\t{item['title']}\t{item.get('url', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
