"""Match file paths against glob patterns.

A pattern uses three wildcards: `**` matches any number of folders, `*` matches
any part of one name, and `?` matches one character. A pattern that ends in a
slash matches everything below that folder.
"""

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern:
    if pattern.endswith("/"):
        pattern += "**"
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, patterns) -> bool:
    """Return True when the path matches any of the patterns."""
    return any(_compile(p).match(path) for p in patterns)
# lab-5: a tier 4 change
