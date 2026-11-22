"""The review of a tier 3 or 4 try: the reviewer reads the change with the change
lens and the security lens. It reads the change as text and runs none of it.

The driver calls `review` with its own way to run the reviewer, then hands the
verdict to the gate as a fact. Tier 1 and 2 pass at once.
"""

from gate.gitio import git

LENSES_BY_TIER = {3: ("change", "security"), 4: ("change", "security")}
DIFF_LIMIT = 120000


def diff(repo, base: str, head: str) -> str:
    """The change as text, cut to DIFF_LIMIT characters."""
    return git(repo, "diff", f"{base}...{head}")[:DIFF_LIMIT]


def review(level: int, ticket: str, change: str, run_role) -> tuple:
    """Return (passed, findings, text).

    run_role(lens, inputs) runs the reviewer and returns its answer:
    {verdict, findings: [{level, text, file, line}]}. A "fail" verdict with no
    blocking finding still fails.
    """
    if level < 3:
        return True, [], f"Not needed for tier {level}."
    findings = []
    for lens in LENSES_BY_TIER[level]:
        data = run_role(lens, {"ticket": ticket, "diff": change, "tier": level})
        found = data.get("findings", [])
        findings += [{**f, "lens": lens} for f in found]
        if data.get("verdict") == "fail" and not any(f.get("level") == "blocking" for f in found):
            findings.append({"lens": lens, "level": "blocking", "text": "the reviewer failed it"})
    blocking = [f for f in findings if f.get("level") == "blocking"]
    lines = [f"- {f.get('level')} ({f['lens']}): {f.get('text', '')}"
             + (f" {f['file']}:{f.get('line', '')}" if f.get("file") else "") for f in findings]
    title = (f"Passed. Tier {level}." if not blocking
             else f"Failed: {len(blocking)} blocking finding(s). Tier {level}.")
    return not blocking, findings, "\n".join([title, *lines])
