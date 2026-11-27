"""Check the writing in a change: the rules a script can find. Python 3, standard library only.

Tollgate copies this one file into a project as .tollgate/checks/check_writing.py.
It runs in two ways:

    python3 .tollgate/checks/check_writing.py            the branch against main, a check of the gate
    python3 .tollgate/checks/check_writing.py --staged   the staged change, before a commit

It fails on:

- a word the word list says to avoid, on a line the change adds to a document;
- a long dash, or a filler word such as "leverage" or "delve", on a line the
  change adds to a document, or in a comment the change adds to a source file:
  `#` lines and docstrings in Python, `//` and `/* */` in JavaScript,
  TypeScript, Go, and Rust;
- a README that does not answer its four questions: what it is, why it exists,
  how to start, and when to use it. With --staged, only when the README is in
  the change;
- on the branch, a commit whose subject is not `type(scope): subject`, or that
  credits an AI;
- a document that points at what its own change removes: a relative link or a
  path in backticks to a file the change deletes or moves, or `path::name` for
  a function or class the change removes. A new link to a file that does not
  exist fails too. A reference that was broken before the change, or an
  example path that never existed, is not reported;
- a Mermaid block that the change adds to a document: a diagram is a spec
  drawn as SVG with the diagram skill.

The word list is CONTEXT.md, in this form: a term in bold, then a line that
starts with `_Avoid_:` and lists the words to avoid, with commas between them.
Text in code (between backticks, or in a fenced block) and words in quotes are not checked.
Files under .tollgate are not checked: Tollgate's roles write them, and no builder may edit them.

It ends with 0 when it finds nothing, 1 when it finds something, and prints one
line for each finding: the file and line, then what to change.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

DOCS = (".md", ".markdown", ".txt", ".rst")
# Files that are not prose to check: pip's requirements and constraints files hold
# package pins, and a changelog is written by a tool, such as release-please, from
# commit subjects. Nobody edits it by hand, so a finding there cannot be fixed.
# The same holds for the files under .tollgate: roles write the analysis, the plan,
# and the tickets, lenses review them, and no builder may edit them.
NOT_PROSE = re.compile(r"(^|/)((requirements|constraints)[\w.-]*\.txt|CHANGELOG\.md)$"
                       r"|^\.tollgate/")
SLASH_COMMENTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs")
SOURCES = (".py",) + SLASH_COMMENTS
WORD_LIST = "CONTEXT.md"
LONG_DASH = "—"
# Filler and the plain word to say instead. An empty word means: cut the sentence.
FILLER = {"leverage": "use", "leverages": "uses", "leveraging": "using", "utilize": "use",
          "utilizes": "uses", "utilizing": "using", "delve": "look", "delves": "looks",
          "it's worth noting": "", "it is worth noting": ""}
TYPES = "feat|fix|docs|test|refactor|chore|build|ci|perf|style|revert"
SUBJECT = re.compile(rf"^({TYPES})\([^()\s]+\)!?: \S")
AI_CREDIT = re.compile(r"co-authored-by:.*\b(claude|anthropic|openai|chatgpt|copilot|gemini)\b"
                       r"|generated (with|by) .*\b(claude|chatgpt|copilot|gemini|ai)\b"
                       r"|\U0001F916", re.IGNORECASE)
# The four questions, each with words a heading or the opening may use for it.
QUESTIONS = {
    "why it exists": r"why|gain|benefit|problem|what you get",
    "how to start": r"start|install|set ?up|quick ?start|getting started|usage|use it",
    "when to use it": r"when|use (it|this) (for|when)|fits|cost",
}


def git(*args, cwd="."):
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


def avoid_words(root: Path) -> dict:
    """{word to avoid: the term to use}, from the word list, if the project has one."""
    path = root / WORD_LIST
    if not path.exists():
        return {}
    out, term = {}, None
    for line in path.read_text().splitlines():
        m = re.match(r"^\*\*([^*]+)\*\*", line)
        if m:
            term = m.group(1).strip()
        m = re.match(r"^_Avoid_:\s*(.+)$", line)
        if m and term:
            for word in m.group(1).split(","):
                word = word.strip().strip(".")
                if word:
                    out[word] = term
    # A word that is itself a term is never one to avoid.
    terms = {t.lower() for t in out.values()}
    return {w: t for w, t in out.items() if w.lower() not in terms}


def prose(line: str) -> str:
    """The line without code, link addresses, and quoted words: a word in quotes is
    named, not used, as in: "the server" alone tells a reader nothing."""
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r'"[^"]*"|\u201c[^\u201d]*\u201d', " ", line)
    line = re.sub(r"\]\([^)]*\)", "]", line)
    line = re.sub(r"https?://\S+", " ", line)
    return re.sub(r"<[^>]+>", " ", line)


def content(root: Path, name: str, staged: bool) -> str:
    """The new text of a file: from the index with --staged, else from HEAD."""
    code, out = git("show", f"{':' if staged else 'HEAD:'}{name}", cwd=root)
    if code == 0:
        return out
    try:
        return (root / name).read_text()
    except OSError:
        return ""


def diff_lines(root: Path, base: str, staged: bool) -> dict:
    """{file: [(line number, text)]} for each line the change adds."""
    span = ["--cached"] if staged else [f"{base}...HEAD"]
    # The prefixes are explicit: a user setting such as diff.mnemonicPrefix changes
    # them, and the parser below reads "+++ b/".
    code, out = git("diff", "--unified=0", "--no-color", "--src-prefix=a/", "--dst-prefix=b/",
                    *span, "--", cwd=root)
    if code != 0:
        return {}
    files, path, number = {}, None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            number = int(re.search(r"\+(\d+)", line).group(1))
        elif path and line.startswith("+") and not line.startswith("+++"):
            files.setdefault(path, []).append((number, line[1:]))
            number += 1
    return files


def is_doc(name: str) -> bool:
    """True for a file of prose that the writing rules apply to."""
    return name.endswith(DOCS) and not NOT_PROSE.search(name)


def added_lines(root: Path, base: str, staged: bool = False) -> dict:
    """{file: [(line number, text)]} for each line the change adds to a document."""
    files = {name: lines for name, lines in diff_lines(root, base, staged).items()
             if is_doc(name) and name != WORD_LIST}
    # Lines inside a fenced code block are code. Read each file to know where they are.
    for name, lines in files.items():
        fenced, inside = set(), False
        for n, text in enumerate(content(root, name, staged).splitlines(), 1):
            if text.lstrip().startswith(("```", "~~~")):
                inside = not inside
                fenced.add(n)
            elif inside:
                fenced.add(n)
        files[name] = [(n, t) for n, t in lines if n not in fenced]
    return files


def python_comments(text: str) -> dict:
    """{line number: the words of its comments and docstrings} in Python source."""
    out = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = out.get(tok.start[0], "") + " " + tok.string.lstrip("#")
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            for n in range(body[0].lineno, body[0].end_lineno + 1):
                # Without the quotes that open and close it: words in quotes are not checked.
                line = lines[n - 1].replace('"""', " ").replace("'''", " ")
                out[n] = out.get(n, "") + " " + line
    return out


def slash_comments(text: str) -> dict:
    """{line number: the words of its comments} in source with // and /* */ comments.
    Strings are skipped, roughly: a quote starts a string that ends at the same quote."""
    out, n, i, state, quote = {}, 1, 0, "code", ""
    while i < len(text):
        c, pair = text[i], text[i:i + 2]
        if c == "\n":
            n += 1
            if state == "line":
                state = "code"
        elif state == "code":
            if pair == "//":
                state, i = "line", i + 1
            elif pair == "/*":
                state, i = "block", i + 1
            elif c in "\"'`":
                state, quote = "string", c
        elif state == "string":
            if c == "\\":
                i += 1
            elif c == quote:
                state = "code"
        elif state == "block" and pair == "*/":
            state, i = "code", i + 1
        else:
            out[n] = out.get(n, "") + c
        i += 1
    return out


def added_comments(root: Path, base: str, staged: bool = False) -> dict:
    """{file: [(line number, comment text)]} for each comment the change adds to source."""
    files = {}
    for name, lines in diff_lines(root, base, staged).items():
        if not name.endswith(SOURCES) or NOT_PROSE.search(name):
            continue
        text = content(root, name, staged)
        found = python_comments(text) if name.endswith(".py") else slash_comments(text)
        kept = [(n, found[n]) for n, _ in lines if found.get(n, "").strip()]
        if kept:
            files[name] = kept
    return files


# The keys of a diagram spec that hold words a person reads in the picture. Ids,
# references, settings, and the field names of a class diagram are not words.
DRAWN = ("title", "desc", "text", "name", "label", "description", "tech", "sub", "head",
         "caption", "event", "guard", "note", "tag", "stereotype", "line", "system", "roles")
_STR = r'"(?:[^"\\]|\\.)*"'
# "key": "words", or "key": ["words", "words"]; an array of objects is read key by key.
DRAWN_VALUE = re.compile(rf'"(\w+)"\s*:\s*({_STR}|\[\s*{_STR}(?:\s*,\s*{_STR})*\s*\])')


def is_diagram_spec(name: str, text: str) -> bool:
    """A diagram spec: a JSON object in a src folder with a title, a description, and a
    diagram type or a flow's nodes."""
    if not name.endswith(".json") or "/src/" not in f"/{name}":
        return False
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        return False
    return (isinstance(spec, dict) and "title" in spec and "desc" in spec
            and ("type" in spec or "nodes" in spec))


def drawn_words(line: str, inside_names: bool) -> str:
    """The words a line of a diagram spec puts in the picture."""
    words = []
    for key, value in DRAWN_VALUE.findall(line):
        if key in DRAWN or inside_names:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                continue
            words += [parsed] if isinstance(parsed, str) else [v for v in parsed
                                                                if isinstance(v, str)]
    return " ".join(words)


def added_drawn_words(root: Path, base: str, staged: bool = False) -> dict:
    """{file: [(line number, words)]} for each line the change adds to a diagram spec."""
    files = {}
    for name, lines in diff_lines(root, base, staged).items():
        text = content(root, name, staged)
        if not is_diagram_spec(name, text):
            continue
        # "names" renames the labels over the boxes: its values are words too.
        names = {n for n, t in enumerate(text.splitlines(), 1) if '"names"' in t}
        kept = [(n, drawn_words(t, n in names)) for n, t in lines]
        kept = [(n, w) for n, w in kept if w.strip()]
        if kept:
            files[name] = kept
    return files


def plain_words(name: str, n: int, words_only: str) -> list:
    """A long dash and filler words: the rules for every word a person reads."""
    found = []
    if LONG_DASH in words_only:
        found.append(f"{name}:{n}: a long dash. Use a colon or a period.")
    for word, plain in FILLER.items():
        if re.search(rf"\b{re.escape(word)}\b", words_only, re.IGNORECASE):
            fix = f"Say '{plain}'." if plain else "Cut the sentence."
            found.append(f"{name}:{n}: '{word}' is filler. {fix}")
    return found


def check_lines(root: Path, base: str, staged: bool = False) -> list:
    words = avoid_words(root)
    # A word written with a capital in the list, such as Action, is a name: only
    # that spelling is matched. Any other word is matched in any case.
    rules = [(re.compile(rf"\b{re.escape(w)}\b", 0 if w != w.lower() else re.IGNORECASE), t)
             for w, t in sorted(words.items(), key=lambda x: -len(x[0]))]
    found = []

    def listed(name, n, words_only):
        taken = set()  # a longer word wins over a shorter one inside it
        for rule, term in rules:
            for m in rule.finditer(words_only):
                if taken.isdisjoint(range(*m.span())):
                    taken.update(range(*m.span()))
                    found.append(f"{name}:{n}: '{m.group(0)}'. The word list says: {term}.")

    for name, lines in added_lines(root, base, staged).items():
        for n, text in lines:
            words_only = prose(text)
            found += plain_words(name, n, words_only)
            listed(name, n, words_only)
    # A diagram's words are read like a document's: the same word list and plain words.
    for name, lines in added_drawn_words(root, base, staged).items():
        for n, words in lines:
            found += plain_words(name, n, words)
            listed(name, n, words)
    # The word list is for documents only: code may name things the list avoids.
    for name, lines in added_comments(root, base, staged).items():
        for n, text in lines:
            found += plain_words(name, n, prose(text))
    return found


LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICKED = re.compile(r"`([^`\s]+)`")
NOT_A_PATH = ("<", "*", "~", "$", "{", "://", "@")
DEFINES = r"^\s*(?:async\s+def|def|class|func|fn|function|const|let|var)\s+{0}\b|^\s*{0}\s*="


def _tree(root: Path, rev: str | None) -> set:
    """The files of a commit, or of the index when rev is None."""
    args = ["ls-files"] if rev is None else ["ls-tree", "-r", "--name-only", rev]
    code, out = git(*args, cwd=root)
    return set(out.splitlines()) if code == 0 else set()


def _text(root: Path, rev: str | None, name: str) -> str:
    code, out = git("show", f"{'' if rev is None else rev}:{name}", cwd=root)
    return out if code == 0 else ""


def _defines(text: str, name: str) -> bool:
    last = re.escape(name.rsplit(".", 1)[-1])
    return bool(re.search(DEFINES.format(last), text, re.MULTILINE))


def _refs(doc: str, text: str):
    """(line number, kind, path, name) for each link and each path in backticks,
    outside fenced code. A link is relative to the doc; a path in backticks may be
    relative to the doc or to the root, so both are given."""
    inside = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            inside = not inside
            continue
        if inside:
            continue
        here = os.path.dirname(doc)
        for m in LINK.finditer(line):
            target = m.group(1).split("#", 1)[0]
            if not target or any(t in target for t in NOT_A_PATH) or target.startswith("mailto:"):
                continue
            path = target[1:] if target.startswith("/") else os.path.join(here, target)
            yield n, "links to", [os.path.normpath(path)], None
        for m in TICKED.finditer(line):
            token = m.group(1)
            if any(t in token for t in NOT_A_PATH) or token.startswith(("-", "/", "..")):
                continue
            path, _, name = token.partition("::")
            path = re.sub(r":\d+$", "", path)
            if "/" not in path and "." not in path:
                continue
            yield n, "names", [os.path.normpath(path), os.path.normpath(os.path.join(here, path))], \
                name or None


def check_docs(root: Path, base: str, staged: bool = False) -> list:
    """Each reference in a document that this change breaks."""
    if staged:
        old_rev, new_rev = "HEAD", None
    else:
        code, out = git("merge-base", base, "HEAD", cwd=root)
        if code != 0:
            return []
        old_rev, new_rev = out.strip(), "HEAD"
    old, new = _tree(root, old_rev), _tree(root, new_rev)
    span = ["--cached"] if staged else [f"{base}...HEAD"]
    code, out = git("diff", "--name-only", *span, cwd=root)
    changed = set(out.splitlines() if code == 0 else []) | (old - new)
    added = {name: {n for n, _ in lines} for name, lines in diff_lines(root, base, staged).items()}
    # Only a removed file or a changed source can break a reference in a doc the
    # change does not touch. Otherwise, check only the docs the change touches.
    reach = old - new or any(not is_doc(c) for c in changed)
    docs = sorted(d for d in new if is_doc(d) and (reach or d in changed))
    found = []
    for doc in docs:
        seen = set()
        for n, kind, paths, name in _refs(doc, _text(root, new_rev, doc)):
            was = [p for p in paths if p in old]
            label = (paths[0] if not was else was[0]) + (f"::{name}" if name else "")
            if (n, label) in seen:
                continue
            if was and not any(p in new for p in was) or was and name and _defines(_text(root, old_rev, was[0]), name) \
                    and not _defines(_text(root, new_rev, was[0]), name):
                seen.add((n, label))
                found.append(f"{doc}:{n}: {kind} {label}, which this change removes. "
                             "Update the doc.")
            elif (not was and kind == "links to" and not any(p in new for p in paths)
                  and n in added.get(doc, ())):
                seen.add((n, label))
                found.append(f"{doc}:{n}: {kind} {label}, which does not exist.")
    return found


def check_mermaid(root: Path, base: str, staged: bool = False) -> list:
    """Each Mermaid block that the change adds to a document."""
    found = []
    for name, lines in diff_lines(root, base, staged).items():
        if is_doc(name):
            found += [f"{name}:{n}: a Mermaid block. Draw the diagram with the diagram skill: "
                      "a spec in a src folder, drawn as SVG."
                      for n, text in lines if text.strip().startswith(("```mermaid", "~~~mermaid"))]
    return found


def check_readme(root: Path) -> list:
    path = root / "README.md"
    if not path.exists():
        return [("README.md: missing. It answers what the project is, why it exists, how to "
                "start, and when to use it.")]
    text = path.read_text()
    lines = [x for x in text.splitlines() if x.strip()]
    opening = next((x for x in lines if not x.startswith(("#", "<", "!", "[", ">"))), "")
    found = []
    if not opening:
        found.append("README.md: no opening sentence that says what the project is.")
    headings = " ".join(x.lower() for x in lines if x.startswith("#"))
    top = " ".join(lines[:12]).lower()
    for question, words in QUESTIONS.items():
        if not re.search(rf"\b({words})", headings) and not re.search(rf"\b({words})", top):
            found.append(f"README.md: does not answer {question}. Give it a heading or a line.")
    return found


def check_commits(root: Path, base: str) -> list:
    code, out = git("log", "--no-merges", "--format=%h%x00%B%x01", f"{base}..HEAD", cwd=root)
    if code != 0:
        return []
    found = []
    for entry in filter(None, (e.strip() for e in out.split("\x01"))):
        sha, _, body = entry.partition("\x00")
        subject = body.strip().splitlines()[0] if body.strip() else ""
        if not SUBJECT.match(subject):
            found.append(f"commit {sha}: subject '{subject[:60]}' is not 'type(scope): subject', "
                         f"with a type from: {TYPES.replace('|', ', ')}.")
        for line in body.splitlines():
            if AI_CREDIT.search(line):
                found.append(f"commit {sha}: '{line.strip()[:60]}' credits an AI. The author "
                             f"is the owner of the repository.")
    return found


def main(repo=".", base="main", staged=False) -> int:
    root = Path(repo).resolve()
    if staged:
        names = diff_lines(root, base, True)
        found = (check_lines(root, base, True) + check_docs(root, base, True)
                 + check_mermaid(root, base, True)
                 + (check_readme(root) if "README.md" in names else []))
    elif git("rev-parse", "--verify", "-q", base, cwd=root)[0] != 0:
        print(f"check_writing: there is no {base} to compare with, so only the README is checked.")
        found = check_readme(root)
    else:
        found = (check_lines(root, base) + check_docs(root, base) + check_mermaid(root, base)
                 + check_readme(root)
                 + check_commits(root, base))
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(staged="--staged" in sys.argv[1:]))
