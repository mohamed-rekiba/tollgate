"""Work out the tier of a change from the files it touches.

Frozen files do not count: the gate checks them separately.
"""

from action.paths import matches


def tier(settings: dict, changes: dict, frozen=()) -> tuple:
    """Return (tier, reason). changes maps a path to the lines it changed."""
    guarded = settings["harness"] + settings["tiers"].get("3", []) + settings["tiers"].get("4", [])
    counted = {p: n for p, n in changes.items() if p not in frozen or matches(p, guarded)}
    for path in sorted(counted):
        if matches(path, settings["harness"]):
            return 4, f"{path} is harness"
    for path in sorted(counted):
        if matches(path, settings["tiers"].get("4", [])):
            return 4, f"{path} matches a tier 4 rule"
    for path in sorted(counted):
        if matches(path, settings["tiers"].get("3", [])):
            return 3, f"{path} matches a tier 3 rule"
    limit = settings["tier1"]
    lines = sum(counted.values())
    if len(counted) <= limit["max_files"] and lines <= limit["max_lines"]:
        return 1, f"{len(counted)} files and {lines} lines"
    return 2, f"{len(counted)} files and {lines} lines"
