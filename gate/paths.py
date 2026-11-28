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


def folder_exists(root: str, folder: str) -> bool:
    """True when root/folder is a folder inside root. The root itself counts."""
    try:
        path = Path(root, folder).resolve()
        return path.is_relative_to(Path(root).resolve()) and path.is_dir()
    except (OSError, TypeError, ValueError):
        return False


def line_exists(root: str, file: str, line) -> bool:
    """True when root/file has a line number `line`, counted from 1."""
    text = read_inside(root, file)
    return text is not None and isinstance(line, int) and 1 <= line <= len(text.splitlines())


# A name is defined when a line starts with one of these words and the name, or
# assigns to it. setup/check_writing.py carries the same patterns, because it runs
# alone in a project; tests/test_analysis.py keeps the two the same.
DEFINES = (r"^\s*(?:async\s+def|def|class|func|fn|function|const|let|var)\s+{0}\b"
           r"|^\s*{0}\s*=")
# The patterns of one language, by the file's suffix, tried as well as DEFINES. Each
# has {0} where the name goes. A language plugs in with one entry here, and the same
# entry in setup/check_writing.py.
LANGUAGE_DEFINES = {
    ".go": (r"^[ \t]*type[ \t]+{0}\b",                    # type Name struct, or an alias
            r"^[ \t]+{0}[ \t]+(?:struct|interface)\b",     # a type in a type ( ... ) block
            r"^func[ \t]*\([^)]*\)[ \t]*{0}[ \t]*[\[(]",    # a method: func (r *T) Name(
            r"^[ \t]+{0}[ \t]*\([^)]*\)[ \t]*[\w(*\[]",    # an interface method with a result
            r"^[ \t]+{0}(?:[ \t]*,[ \t]*\w+)*[ \t]+[\w.*\[\]]+[ \t]*="),  # a const or var in a block
    ".rs": ((r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:async[ \t]+)?(?:unsafe[ \t]+)?"
            r"(?:fn|struct|enum|trait|type|mod|const|static|union)[ \t]+{0}\b"),),
    ".ts": ((r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:abstract[ \t]+)?"
            r"(?:interface|type|enum|class|function|const|let|var)[ \t]+{0}\b"),),
    ".tsx": ((r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?"
             r"(?:interface|type|enum|class|function|const)[ \t]+{0}\b"),),
    ".js": ((r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?"
            r"(?:class|function|const|let|var)[ \t]+{0}\b"),),
}


def defines(text: str, name: str, path: str = "") -> bool:
    """True when text, the file at path, defines `name`: the last part after a dot."""
    last = re.escape(name.rsplit(".", 1)[-1])
    suffix = path[path.rfind("."):] if "." in path.rsplit("/", 1)[-1] else ""
    patterns = (DEFINES, *LANGUAGE_DEFINES.get(suffix, ()))
    return any(re.search(p.format(last), text, re.MULTILINE) for p in patterns)


def name_exists(root: str, file: str, name: str) -> bool:
    """True when root/file defines `name`: a function, a class, a type, or an assignment,
    by DEFINES and the patterns of the file's language."""
    text = read_inside(root, file)
    return text is not None and defines(text, name, file)


def heading_exists(root: str, file: str, heading: str) -> bool:
    """True when root/file has a markdown heading, of any level, with this text. A line
    inside a fenced code block is not a heading."""
    text = read_inside(root, file)
    want = heading.strip()
    if text is None or not want:
        return False
    fence = None    # the open fence: its character and its length
    for line in text.splitlines():
        m = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2).strip():
                fence = None
        elif m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
        else:
            h = re.match(r"#{1,6}[ \t]+(.*?)[ \t]*$", line)
            if h and h.group(1) == want:
                return True
    return False


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
