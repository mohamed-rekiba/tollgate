"""List every question that waits for you, and answer one. It reads the store.

    python3 -m setup.inbox [--home .]                         every project of a home
    python3 -m setup.inbox --project .                        one project
    python3 -m setup.inbox --project . answer <n> <decision> [hint]

A question waits until you answer it. The answer's first line is the decision,
one of the question's options, then an optional hint for the role that reads it.
"""

import argparse
import sys
from pathlib import Path

from gate.store import Store, StoreError
from setup.home import HomeError, load


def projects(home: str | None, project: str | None) -> list:
    if project:
        return [str(Path(project).resolve())]
    return [str(Path(home, p["path"]).resolve()) for p in load(home)["projects"]]


def inbox(paths: list, store=Store) -> list:
    """[{project, n, title, options}] for each open question."""
    out = []
    for path in paths:
        try:
            questions = store(path).open_questions()
        except (StoreError, OSError) as err:
            out.append({"project": path, "n": None, "title": f"cannot read: {err}", "options": []})
            continue
        for n, q in sorted(questions.items()):
            out.append({"project": path, "n": n, "title": q.get("title", ""),
                        "options": q.get("options") or []})
    return out


def answer(path: str, n: int, decision: str, hint: str = "", store=Store) -> None:
    question = store(path).open_questions().get(n)
    if question is None:
        raise StoreError(f"question {n} is not open")
    options = question.get("options") or []
    if options and decision not in options:
        raise StoreError(f"{decision} is not an option. The options: {', '.join(options)}")
    store(path).answer(n, f"{decision} {hint}".strip())


def main(argv=None, store=Store) -> int:
    parser = argparse.ArgumentParser(prog="inbox", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--home", default=".")
    parser.add_argument("--project")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("answer")
    p.add_argument("n", type=int)
    p.add_argument("decision")
    p.add_argument("hint", nargs="*")
    args = parser.parse_args(argv)
    try:
        if args.command == "answer":
            answer(projects(args.home, args.project or ".")[0], args.n, args.decision,
                   " ".join(args.hint), store)
            print(f"answered question {args.n}")
            return 0
        found = inbox(projects(args.home, args.project), store)
    except NotImplementedError:
        print("inbox: UNFINISHED: the store cannot read questions yet.", file=sys.stderr)
        return 2
    except (HomeError, StoreError, OSError) as err:
        print(f"inbox: {err}", file=sys.stderr)
        return 1
    if not found:
        print("Nothing waits for you.")
    for item in found:
        options = f"  options: {', '.join(item['options'])}" if item["options"] else ""
        print(f"{item['project']}  question {item['n']}: {item['title']}{options}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
