"""Check the writing in a change: the rules a script can find. Python 3, standard library only.

The docs skill copies this one file into a project as
.tollgate/checks/check_writing.py, and the project runs it from its root as one
of its checks:

    python3 .tollgate/checks/check_writing.py

It compares the change with origin/main and fails on:

- a word the word list says to avoid, on a line the change adds to a document;
- a long dash on a line the change adds to a document;
- a README that does not answer its four questions: what it is, why it exists,
  how to start, and when to use it;
- a commit in the change whose subject is not `type(scope): subject`, or that
  credits an AI.

The word list is CONTEXT.md, in this form: a term in bold, then a line that
starts with `_Avoid_:` and lists the words to avoid, with commas between them.
Text in code (between backticks, or in a fenced block) and words in quotes are not checked.

It ends with 0 when it finds nothing, 1 when it finds something, and prints one
line for each finding: the file and line, then what to change.
"""

import re
import subprocess
import sys
from pathlib import Path

DOCS = (".md", ".markdown", ".txt", ".rst")
WORD_LIST = "CONTEXT.md"
LONG_DASH = "—"
TYPES = "feat|fix|docs|test|refactor|chore|build|ci|perf|style|revert"
SUBJECT = re.compile(rf"^({TYPES})(\([^()\s]+\))?!?: \S")
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


def added_lines(root: Path, base: str) -> dict:
    """{file: [(line number, text)]} for each line the change adds to a document."""
    code, out = git("diff", "--unified=0", "--no-color", f"{base}...HEAD", "--", cwd=root)
    if code != 0:
        return {}
    files, path, number = {}, None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            name = line[6:] if line.startswith("+++ b/") else None
            path = name if name and name.endswith(DOCS) and name != WORD_LIST else None
        elif line.startswith("@@"):
            number = int(re.search(r"\+(\d+)", line).group(1))
        elif path and line.startswith("+") and not line.startswith("+++"):
            files.setdefault(path, []).append((number, line[1:]))
            number += 1
    # Lines inside a fenced code block are code. Read each file to know where they are.
    for name, lines in files.items():
        fenced, inside = set(), False
        try:
            for n, text in enumerate((root / name).read_text().splitlines(), 1):
                if text.lstrip().startswith(("```", "~~~")):
                    inside = not inside
                    fenced.add(n)
                elif inside:
                    fenced.add(n)
        except OSError:
            continue
        files[name] = [(n, t) for n, t in lines if n not in fenced]
    return files


def check_lines(root: Path, base: str) -> list:
    words = avoid_words(root)
    # A word written with a capital in the list, such as Action, is a name: only
    # that spelling is matched. Any other word is matched in any case.
    rules = [(re.compile(rf"\b{re.escape(w)}\b", 0 if w != w.lower() else re.IGNORECASE), t)
             for w, t in sorted(words.items(), key=lambda x: -len(x[0]))]
    found = []
    for name, lines in added_lines(root, base).items():
        for n, text in lines:
            words_only = prose(text)
            if LONG_DASH in words_only:
                found.append(f"{name}:{n}: a long dash. Use a colon or a period.")
            taken = set()  # a longer word wins over a shorter one inside it
            for rule, term in rules:
                for m in rule.finditer(words_only):
                    if taken.isdisjoint(range(*m.span())):
                        taken.update(range(*m.span()))
                        found.append(f"{name}:{n}: '{m.group(0)}'. The word list says: {term}.")
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


def main(repo=".", base="origin/main") -> int:
    root = Path(repo).resolve()
    if git("rev-parse", "--verify", "-q", base, cwd=root)[0] != 0:
        print(f"check_writing: there is no {base} to compare with, so only the README is checked.")
        found = check_readme(root)
    else:
        found = check_lines(root, base) + check_readme(root) + check_commits(root, base)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
