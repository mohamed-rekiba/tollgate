"""Match file paths against glob patterns, and check that a cited line exists.

A pattern uses three wildcards: `**` matches any number of folders, `*` matches
any part of one name, and `?` matches one character. A pattern that ends in a
slash matches everything below that folder.
"""

import re
from functools import lru_cache
from pathlib import Path


def read_inside(root: str, file: str) -> str | None:
    """The text of root/file, or None when it is missing, unreadable, or outside root."""
    try:
        path = Path(root, file).resolve()
        if not path.is_relative_to(Path(root).resolve()):
            return None
        return path.read_text()
    except (OSError, UnicodeDecodeError, TypeError, ValueError):
        return None


def line_exists(root: str, file: str, line) -> bool:
    """True when root/file has a line number `line`, counted from 1."""
    text = read_inside(root, file)
    return text is not None and isinstance(line, int) and 1 <= line <= len(text.splitlines())


# A name is defined when a line starts with one of these words and the name, or
# assigns to it. setup/check_writing.py carries the same pattern, because it runs
# alone in a project; tests/test_analysis.py keeps the two the same.
DEFINES = (r"^\s*(?:async\s+def|def|class|func|fn|function|const|let|var)\s+{0}\b"
           r"|^\s*{0}\s*=")


def name_exists(root: str, file: str, name: str) -> bool:
    """True when root/file defines `name`: a function, a class, or an assignment."""
    text = read_inside(root, file)
    last = re.escape(name.rsplit(".", 1)[-1])
    return text is not None and bool(re.search(DEFINES.format(last), text, re.MULTILINE))


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
