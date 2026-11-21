"""Count invented names in a change: names that do not exist in the code.

    python3 docs/experiments/e310/invented_names.py --repo . --base origin/main --head <sha>

For each Python file the change adds or edits, at the head commit:
- an import of a module that is in neither the project nor the installed Python,
- a name imported from a project module that the module does not define,
- an undefined name, as ruff reports it (F821).

It prints one JSON line: {"head", "invented": n, "names": [...]}. It reads the
change as files and runs none of it.
"""

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True,
                          check=True).stdout


def count(repo: str, base: str, head: str) -> dict:
    changed = [p for p in git(repo, "diff", "--name-only", "--diff-filter=AM", f"{base}...{head}")
               .split() if p.endswith(".py")]
    with tempfile.TemporaryDirectory() as tree:
        subprocess.run(f"git -C {repo} archive {head} | tar -x -C {tree}", shell=True, check=True)
        names = []
        for path in changed:
            source = Path(tree, path)
            try:
                module = ast.parse(source.read_text())
            except (OSError, SyntaxError) as err:
                names.append(f"{path}: does not parse ({err.__class__.__name__})")
                continue
            for node in ast.walk(module):
                if isinstance(node, ast.Import):
                    targets = [(a.name, None) for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    targets = [(node.module, a.name) for a in node.names]
                else:
                    continue
                for mod, name in targets:
                    local = Path(tree, *mod.split(".")).with_suffix(".py")
                    package = Path(tree, *mod.split("."), "__init__.py")
                    if local.exists() or package.exists():
                        if name and name != "*":
                            text = (local if local.exists() else package).read_text()
                            defined = {n.name for n in ast.walk(ast.parse(text))
                                       if isinstance(n, (ast.FunctionDef, ast.ClassDef,
                                                         ast.AsyncFunctionDef))}
                            defined |= {t.id for n in ast.walk(ast.parse(text))
                                        if isinstance(n, ast.Assign) for t in n.targets
                                        if isinstance(t, ast.Name)}
                            defined |= {a.asname or a.name.split(".")[0]
                                        for n in ast.walk(ast.parse(text))
                                        if isinstance(n, (ast.Import, ast.ImportFrom))
                                        for a in n.names}
                            sub = Path(tree, *mod.split("."), f"{name}.py")
                            if name not in defined and not sub.exists():
                                names.append(f"{path}: {mod}.{name}")
                    elif importlib.util.find_spec(mod.split(".")[0]) is None:
                        names.append(f"{path}: module {mod}")
        if changed:
            out = subprocess.run(["ruff", "check", "--select", "F821", "--output-format", "json",
                                  *changed], cwd=tree, capture_output=True, text=True, check=False)
            try:
                for item in json.loads(out.stdout or "[]"):
                    names.append(f"{item['filename'].replace(tree + '/', '')}: {item['message']}")
            except json.JSONDecodeError:
                pass
    return {"head": head, "invented": len(names), "names": names}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(count(args.repo, args.base, args.head)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
