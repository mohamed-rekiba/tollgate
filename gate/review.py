"""The review of a try: the reviewer reads the change with the review lens, and
from tier 3 with the security lens too. It reads the change as text and runs
none of it.

The driver calls `review` with its own way to run the reviewer, then hands the
verdict to the gate as a fact. Tier 1 passes at once. A finding counts only when
it points to a file and a line inside the change: the rest are dropped, so a
reviewer cannot fail a try on a guess.
"""

import re

from gate.gitio import git

LENSES_BY_TIER = {1: (), 2: ("review",), 3: ("review", "security"), 4: ("review", "security")}
DIFF_LIMIT = 120000
LEVELS = ("blocking", "major", "minor")   # the worst first
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def diff(repo, base: str, head: str) -> str:
    """The change as text, cut to DIFF_LIMIT characters."""
    return git(repo, "diff", f"{base}...{head}")[:DIFF_LIMIT]


def changed_lines(change: str) -> dict:
    """{path: set of line numbers} that each hunk of the diff covers on the new side."""
    out, path = {}, None
    for line in change.splitlines():
        if line.startswith("+++ "):
            name = line[4:].strip()
            path = None if name == "/dev/null" else name.removeprefix("b/")
            if path:
                out.setdefault(path, set())
        elif path and (m := HUNK.match(line)):
            start, count = int(m[1]), int(m[2] if m[2] is not None else 1)
            out[path].update(range(start, start + max(count, 1)))
    return out


def in_change(finding: dict, lines: dict) -> bool:
    line = finding.get("line")
    return finding.get("file") in lines and isinstance(line, int) and line in lines[finding["file"]]


def review(level: int, ticket: str, change: str, run_role, lenses=None) -> tuple:
    """Return (passed, findings, text).

    run_role(lens, inputs) runs the reviewer and returns its answer:
    {verdict, findings: [{level, text, file, line}]}. A "fail" verdict with no
    blocking finding at all still fails. `lenses` replaces the tier's lenses, for
    the review of a whole task.
    """
    lenses = LENSES_BY_TIER[level] if lenses is None else lenses
    if not lenses:
        return True, [], f"Not needed for tier {level}."
    lines = changed_lines(change)
    findings, dropped = [], 0
    for lens in lenses:
        data = run_role(lens, {"ticket": ticket, "diff": change, "tier": level})
        found = data.get("findings", [])
        kept = [f for f in found if in_change(f, lines)]
        dropped += len(found) - len(kept)
        findings += [{**f, "lens": lens} for f in kept]
        if data.get("verdict") == "fail" and not any(f.get("level") == "blocking" for f in found):
            findings.append({"lens": lens, "level": "blocking", "text": "the reviewer failed it"})
    findings.sort(key=lambda f: LEVELS.index(f.get("level")) if f.get("level") in LEVELS
                  else len(LEVELS))
    blocking = [f for f in findings if f.get("level") == "blocking"]
    out = [f"- {f.get('level')} ({f['lens']}): {f.get('text', '')}"
           + (f" {f['file']}:{f.get('line', '')}" if f.get("file") else "") for f in findings]
    if dropped:
        out.append(f"The review dropped {dropped} finding(s) that point outside the change.")
    title = (f"Passed. Tier {level}." if not blocking
             else f"Failed: {len(blocking)} blocking finding(s). Tier {level}.")
    return not blocking, findings, "\n".join([title, *out])
