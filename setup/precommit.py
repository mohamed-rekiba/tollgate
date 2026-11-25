"""Write the pre-commit config of a project, and copy Tollgate's checks into it.

    python3 -m setup.precommit [--project .] [--replace]

The config holds three kinds of hooks:

- Tollgate's checks, copied into .tollgate/checks/. The plugin's folder changes
  on each update, so the project carries its own copy. Each is a stdlib script,
  and each hook runs it with uv (`uv run --no-project python`), so the hook does not
  depend on which python3 is first on the PATH. It needs no network and no project file.
- The project's checks from .tollgate/settings.json, before each push. Two or more
  checks run side by side in one hook, run_checks.py, unless `parallel` is false.
- The standard tool of each language the project uses, only when the project
  already uses that tool: a tool counts as used when its config file is there.
  Go's formatter has no config file, so every Go project gets it.

It refuses to replace a config that Tollgate did not write, unless --replace. A config
that Tollgate wrote with an older entry (python3) is rewritten with uv, with no --replace.
Running it twice gives the same files. It prints each path that changed.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = ".pre-commit-config.yaml"
CHECKS_DIR = ".tollgate/checks"
SETTINGS = ".tollgate/settings.json"
MARK = "# Written by Tollgate: python3 -m setup.precommit."
SCRIPTS = ("check_locked.py", "check_writing.py", "check_commit_msg.py", "check_merge.py",
           "run_checks.py")
HOOK_TYPES = ("pre-commit", "commit-msg", "pre-merge-commit", "pre-push")

RUN = "uv run --no-project python"

# Tollgate's own hooks: id, name, entry, stages, and whether pre-commit passes file names.
TOLLGATE_HOOKS = [
    ("tollgate-locked", "Tollgate: no change to a locked file",
     f"{RUN} .tollgate/checks/check_locked.py", ["pre-commit", "pre-merge-commit"], False),
    ("tollgate-writing", "Tollgate: plain words",
     f"{RUN} .tollgate/checks/check_writing.py --staged", ["pre-commit"], False),
    ("tollgate-commit-msg", "Tollgate: commit message",
     f"{RUN} .tollgate/checks/check_commit_msg.py", ["commit-msg"], True),
    ("tollgate-merge", "Tollgate: a merge into main passed the gate",
     f"{RUN} .tollgate/checks/check_merge.py merge", ["pre-merge-commit"], False),
    ("tollgate-push", "Tollgate: each commit on main passed the gate",
     f"{RUN} .tollgate/checks/check_merge.py push", ["pre-push"], False),
]

LANGUAGES = {
    "python": {"files": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
               "ends": (".py",)},
    "javascript": {"files": ("package.json",), "ends": (".js", ".jsx", ".mjs", ".cjs", ".ts",
                                                        ".tsx")},
    "go": {"files": ("go.mod",), "ends": (".go",)},
    "rust": {"files": ("Cargo.toml",), "ends": (".rs",)},
}

JS_FILES = r"\.(js|jsx|mjs|cjs|ts|tsx)$"


class PrecommitError(RuntimeError):
    pass


def project_files(root: Path) -> list:
    proc = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                          cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return proc.stdout.splitlines()
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]


def languages(root: Path) -> list:
    names = project_files(root)
    base = {Path(n).name for n in names if "/" not in n}
    return [lang for lang, rule in LANGUAGES.items()
            if base & set(rule["files"]) or any(n.endswith(rule["ends"]) for n in names)]


def _text(root: Path, name: str) -> str:
    try:
        return (root / name).read_text()
    except OSError:
        return ""


def _any(root: Path, *patterns) -> bool:
    return any(next(root.glob(p), None) for p in patterns)


def _js_uses(root: Path, tool: str) -> bool:
    try:
        package = json.loads(_text(root, "package.json") or "{}")
    except ValueError:
        return False
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    return tool in deps or tool in package


def tool_hooks(root: Path) -> list:
    """The standard tool hooks for the languages and tools the project uses."""
    found = languages(root)
    pyproject = _text(root, "pyproject.toml")
    hooks = []
    if "python" in found:
        if _any(root, "ruff.toml", ".ruff.toml") or "[tool.ruff" in pyproject:
            hooks.append({"id": "ruff", "name": "ruff", "entry": "ruff check --force-exclude",
                          "types": ["python"]})
        if "[tool.black" in pyproject:
            hooks.append({"id": "black", "name": "black", "entry": "black --check",
                          "types": ["python"]})
        if _any(root, "mypy.ini", ".mypy.ini") or "[tool.mypy" in pyproject:
            hooks.append({"id": "mypy", "name": "mypy", "entry": "mypy", "types": ["python"]})
    if "javascript" in found:
        if _any(root, "eslint.config.*", ".eslintrc*") or _js_uses(root, "eslint"):
            hooks.append({"id": "eslint", "name": "eslint", "entry": "npx --no-install eslint",
                          "files": JS_FILES})
        if _any(root, ".prettierrc*", "prettier.config.*") or _js_uses(root, "prettier"):
            hooks.append({"id": "prettier", "name": "prettier",
                          "entry": "npx --no-install prettier --check", "files": JS_FILES})
    if "go" in found:
        hooks.append({"id": "gofmt", "name": "gofmt",
                      "entry": "sh -c 'test -z \"$(gofmt -l \"$@\")\"' --", "types": ["go"]})
        if _any(root, ".golangci.*"):
            hooks.append({"id": "golangci-lint", "name": "golangci-lint",
                          "entry": "golangci-lint run", "types": ["go"],
                          "pass_filenames": False})
    if "rust" in found:
        if _any(root, "rustfmt.toml", ".rustfmt.toml"):
            hooks.append({"id": "rustfmt", "name": "rustfmt", "entry": "cargo fmt -- --check",
                          "types": ["rust"], "pass_filenames": False})
        if _any(root, "clippy.toml", ".clippy.toml"):
            hooks.append({"id": "clippy", "name": "clippy",
                          "entry": "cargo clippy -- -D warnings", "types": ["rust"],
                          "pass_filenames": False})
    return hooks


def settings_hooks(settings: dict) -> list:
    """The checks in the settings, before each push. The writing check is already a
    hook of its own. pre-commit runs hooks one after another, so two or more checks
    get one hook that runs them side by side with run_checks.py, unless the setting
    `parallel` is false: then each check gets a hook of its own, as before."""
    found = [(name, check) for name, check in sorted(settings.get("checks", {}).items())
             if name != "writing" and "check_writing.py" not in check.get("run", "")]
    if len(found) > 1 and settings.get("parallel", True) is not False:
        return [{"id": "tollgate-checks", "name": "Tollgate checks, side by side",
                 "entry": f"{RUN} .tollgate/checks/run_checks.py", "pass_filenames": False,
                 "always_run": True, "stages": ["pre-push"]}]
    hooks = []
    for name, check in found:
        hooks.append({"id": f"tollgate-check-{name}", "name": f"Tollgate check: {name}",
                      "entry": "sh -c", "args": [check["run"]], "pass_filenames": False,
                      "always_run": True, "stages": ["pre-push"]})
    return hooks


def _q(value) -> str:
    # A JSON string is a YAML string in double quotes.
    return json.dumps(value)


def _hook(hook: dict) -> list:
    lines = [f"  - id: {hook['id']}", f"    name: {_q(hook['name'])}",
             f"    entry: {_q(hook['entry'])}", "    language: system"]
    for key in ("args", "types", "stages"):
        if key in hook:
            lines.append(f"    {key}: [{', '.join(_q(v) for v in hook[key])}]")
    if "files" in hook:
        lines.append(f"    files: {_q(hook['files'])}")
    for key in ("pass_filenames", "always_run"):
        if key in hook:
            lines.append(f"    {key}: {'true' if hook[key] else 'false'}")
    return lines


def render(settings: dict, root: Path) -> str:
    ours = [{"id": i, "name": n, "entry": e, "stages": s, "pass_filenames": p,
             **({} if p else {"always_run": True})} for i, n, e, s, p in TOLLGATE_HOOKS]
    lines = [MARK, "# Change the checks in .tollgate/settings.json, then run /tollgate:init.",
             f"default_install_hook_types: [{', '.join(HOOK_TYPES)}]",
             "default_stages: [pre-commit]", "repos:", "- repo: local", "  hooks:"]
    for hook in ours + settings_hooks(settings) + tool_hooks(root):
        lines += _hook(hook)
    return "\n".join(lines) + "\n"


def write(project: str = ".", replace: bool = False) -> list:
    """Copy the checks and write the config. Return the paths that changed."""
    root = Path(project)
    path = root / SETTINGS
    settings = json.loads(path.read_text()) if path.exists() else {}
    changed = []
    for name in SCRIPTS:
        target = root / CHECKS_DIR / name
        data = (HERE / name).read_bytes()
        if not target.exists() or target.read_bytes() != data:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / name, target)
            changed.append(f"{CHECKS_DIR}/{name}")
    config = root / CONFIG
    text = render(settings, root)
    if config.exists():
        old = config.read_text()
        if not old.startswith(MARK) and not replace:
            raise PrecommitError(f"{CONFIG} was not written by Tollgate. Move its hooks into "
                                 "the checks of the settings, then run again with --replace.")
        if old == text:
            return changed
    config.write_text(text)
    changed.append(CONFIG)
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="precommit", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    try:
        changed = write(args.project, args.replace)
    except (PrecommitError, OSError, ValueError) as err:
        print(f"precommit: {err}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"changed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
