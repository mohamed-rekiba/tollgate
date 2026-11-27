"""Write Tollgate's roles as Claude Code subagents, in the plugin's agents/ folder.

    python3 -m setup.agents           # write agents/<role>.md for each roles/<role>.md
    python3 -m setup.agents --check   # end with 1 if one is out of date

roles/<role>.md is the source. Each agent file adds a header for Claude Code: the
role's name, when to use it, its tools, the same tools the driver gives the
role in driver/roles.py, and the most turns it may take. Edit the role file, then run this.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from driver.roles import TOOLS

# What each role does, in one line, for the agent's description.
DOES = {
    "analyst": "Reads the project and reports what it finds, with citations, before a plan.",
    "test_writer": "Writes the locked tests for one ticket, before anything is built.",
    "builder": "Writes the plan of a task, or builds one ticket in the builder's copy.",
    "reviewer": "Reads tests, a plan, or a change through a lens, and reports findings.",
    "advisor": "Decides what happens after the loop stops, or at a checkpoint.",
}
# The most turns each role may take in your session. The builder builds, the test
# writer writes tests, and the others only read, so they get few.
MAX_TURNS = {"builder": 150, "test_writer": 80, "analyst": 40, "reviewer": 30, "advisor": 15}
ONLY = ("Only when Tollgate's driver names this role in a task; never for other work, "
        "and never on your own.")
HEADER = ("Tollgate's driver starts you and gives you your inputs in the message that "
          "starts you: a json block under Inputs, and for a review, the lens to read with. "
          "Work only in the folder that message names, the copy: start each command with "
          "a cd to it, and give each file its full path in it. "
          "Do what the role below says, and end your answer the way it says.")


def render(role: str) -> str:
    tools = ", ".join(TOOLS[role])
    return (f"---\nname: {role}\ndescription: {DOES[role]} {ONLY}\ntools: {tools}\n"
            f"model: inherit\nmaxTurns: {MAX_TURNS[role]}\n---\n\n{HEADER}\n\n" + (ROOT / "roles" / f"{role}.md").read_text())


def build(check: bool = False) -> list:
    """Write agents/<role>.md for each role file. Return the files that changed,
    or with check, that would; a stale agent with no role file counts too."""
    folder = ROOT / "agents"
    roles = sorted(p.stem for p in (ROOT / "roles").glob("*.md"))
    stale = [p.name for p in folder.glob("*.md") if p.stem not in roles]
    for role in roles:
        target = folder / f"{role}.md"
        text = render(role)
        if not target.exists() or target.read_text() != text:
            stale.append(target.name)
            if not check:
                folder.mkdir(exist_ok=True)
                target.write_text(text)
    if not check:
        for p in folder.glob("*.md"):
            if p.stem not in roles:
                p.unlink()
    return sorted(stale)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m setup.agents", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="change nothing; end with 1 if stale")
    args = parser.parse_args(argv)
    stale = build(args.check)
    for name in stale:
        print(("out of date: " if args.check else "wrote ") + f"agents/{name}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
