"""Write Tollgate's hook into the pre-commit config of a project, and copy Tollgate's checks.

    python3 -m setup.precommit [--project .]

The config is the project's own. Tollgate adds or updates one hook in it, `tollgate`,
and keeps every other repo, hook, and line as it is, in its order:

- Tollgate's own checks are copied into .tollgate/checks/. The plugin's folder changes
  on each update, so the project carries its own copy. One script, tollgate_checks.py,
  runs the checks of a git step side by side, and the hook `tollgate` runs it, for all
  four steps. pre-commit does not tell a hook its step, so the script works it out (see
  tollgate_checks.py). The hook runs it with uv (`uv run --no-project python`), so it does
  not depend on which python3 is first on the PATH. It needs no network and no project
  file. In Tollgate's own project the hook runs setup/tollgate_checks.py, the source, and
  no copy is made.
- The project's checks are hooks of the project, such as `check-tests`. pre-commit runs
  them, and the settings name the hook of each check: `"tests": {"hook": "check-tests"}`.
  A check that an older Tollgate kept as a command in the settings, under `run`, is
  written once as a local hook `check-<name>` that runs at a push, and the settings then
  name that hook. The writing check is one of Tollgate's own, so it keeps its command.
- A config that does not exist yet also gets the standard tool of each language the
  project uses, only when the project already uses that tool: a tool counts as used when
  its config file is there. Go's formatter has no config file, so every Go project gets
  it. A config that exists keeps the tools it has.

The config needs `default_install_hook_types` with the four git steps, so that
`pre-commit install` installs each of them: init adds the steps that are missing.
The hooks of an older Tollgate, whose ids start with `tollgate-`, are removed. Running
it twice gives the same files. It prints each path that changed.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from gate import precommit_config as pc

HERE = Path(__file__).resolve().parent
CONFIG = pc.CONFIG
CHECKS_DIR = ".tollgate/checks"
SETTINGS = ".tollgate/settings.json"
HEADER = ["# Tollgate: /tollgate:init writes the hook tollgate and keeps every other line.",
          "# The other hooks are the project's own. The settings name the ones the gate runs."]
# The header lines that an older Tollgate wrote.
OLD_HEADER = ("# Written by Tollgate: python3 -m setup.precommit.",
              "# Change the checks in .tollgate/settings.json, then run /tollgate:init.")
# The hooks of an older Tollgate, such as tollgate-pre-push, have ids that start with this.
# The hook `tollgate` replaces them.
RETIRED_PREFIX = "tollgate-"
# The check that keeps its command in the settings: Tollgate's own writing check.
OWN_CHECK = "writing"
SCRIPTS = ("check_locked.py", "check_writing.py", "check_commit_msg.py", "check_merge.py",
           "tollgate_checks.py")
# Copies an older Tollgate made, which this one no longer uses.
RETIRED = ("run_checks.py",)
HOOK_TYPES = ("pre-commit", "commit-msg", "pre-merge-commit", "pre-push")

RUN = "uv run --no-project python"

# Tollgate's own checks: one entry, for all four stages. pre-commit passes the commit
# message file at the commit-msg stage and the changed files at the others, so `files`
# keeps only the message files, and the script gets no list of changed files.
STAGE_FILES = r"(^|/)(COMMIT_EDITMSG|MERGE_MSG|SQUASH_MSG|TAG_EDITMSG)$"
TOLLGATE_HOOK = {"id": "tollgate", "name": "Tollgate: the checks of each git step",
                 "stages": list(HOOK_TYPES), "files": STAGE_FILES, "pass_filenames": True,
                 "always_run": True}

LANGUAGES = {
    "python": {"files": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
               "ends": (".py",)},
    "javascript": {"files": ("package.json",), "ends": (".js", ".jsx", ".mjs", ".cjs", ".ts",
                                                        ".tsx")},
    "go": {"files": ("go.mod",), "ends": (".go",)},
    "rust": {"files": ("Cargo.toml",), "ends": (".rs",)},
}

JS_FILES = r"\.(js|jsx|mjs|cjs|ts|tsx)$"


class PrecommitError(ValueError):
    """The config is in a form that Tollgate cannot change without a loss."""


def is_tollgate(root: Path) -> bool:
    """True for Tollgate's own project: it holds the checks as source, in setup/."""
    return all((root / "setup" / name).is_file() for name in ("precommit.py", "tollgate_checks.py"))


def checks_dir(root: Path) -> str:
    """The folder that the config runs Tollgate's checks from."""
    return "setup" if is_tollgate(root) else CHECKS_DIR


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


def _q(value) -> str:
    # A JSON string is a YAML string in double quotes.
    return json.dumps(value)


def hook_lines(hook: dict, indent: int = 2, column: int = 4) -> list:
    """The lines of one hook, with its dash at indent and its keys at column."""
    pad = " " * column
    lines = [f"{' ' * indent}-{' ' * (column - indent - 1)}id: {hook['id']}",
             f"{pad}name: {_q(hook['name'])}", f"{pad}entry: {_q(hook['entry'])}",
             f"{pad}language: system"]
    for key in ("args", "types", "stages"):
        if key in hook:
            lines.append(f"{pad}{key}: [{', '.join(_q(v) for v in hook[key])}]")
    if "files" in hook:
        lines.append(f"{pad}files: {_q(hook['files'])}")
    for key in ("pass_filenames", "always_run"):
        if key in hook:
            lines.append(f"{pad}{key}: {'true' if hook[key] else 'false'}")
    return lines


def tollgatehook_lines(root: Path) -> dict:
    return {**TOLLGATE_HOOK, "entry": f"{RUN} {checks_dir(root)}/tollgate_checks.py"}


def projecthook_lines(name: str, command: str) -> dict:
    """The local hook for a check that an older Tollgate kept as a command in the settings.
    It runs at a push, on the whole project, as Tollgate ran it."""
    return {"id": f"check-{name}", "name": f"check: {name}", "entry": "sh -c",
            "args": [command], "pass_filenames": False, "always_run": True,
            "stages": ["pre-push"]}


def migrate_checks(checks: dict) -> tuple:
    """(checks, hooks): the checks with each command under `run` replaced by the name of
    its hook, and the hooks to write. The writing check keeps its command."""
    out, hooks = {}, []
    for name, check in checks.items():
        if name == OWN_CHECK or not isinstance(check, dict) or "run" not in check:
            out[name] = check
            continue
        hook = projecthook_lines(name, check["run"])
        hooks.append(hook)
        out[name] = {"hook": hook["id"], **{k: v for k, v in check.items() if k != "run"}}
    return out, hooks


def render(settings: dict, root: Path) -> str:
    """A new config: the header, the hook `tollgate`, the hooks of the checks that the
    settings still keep as commands, and the standard tools the project uses."""
    _, moved = migrate_checks(settings.get("checks", {}))
    lines = [*HEADER, f"default_install_hook_types: [{', '.join(HOOK_TYPES)}]",
             "default_stages: [pre-commit]", "repos:", "- repo: local", "  hooks:"]
    for hook in [tollgatehook_lines(root), *moved, *tool_hooks(root)]:
        lines += hook_lines(hook)
    return "\n".join(lines) + "\n"


def _top_key(lines: list, key: str) -> int | None:
    return next((n for n, line in enumerate(lines)
                 if line.startswith(f"{key}:") or line == key + ":"), None)


def _install_types(lines: list) -> list:
    """The lines with each of the four git steps in default_install_hook_types."""
    n = _top_key(lines, "default_install_hook_types")
    if n is None:
        first = next((i for i, line in enumerate(lines) if not line.startswith("#")), len(lines))
        return lines[:first] + [f"default_install_hook_types: [{', '.join(HOOK_TYPES)}]"] + \
            lines[first:]
    value = lines[n].split(":", 1)[1]
    end = n + 1
    if value.strip() and not value.strip().startswith("#"):
        have = pc.flow_list(value)
    else:
        have = []
        while end < len(lines) and lines[end].lstrip().startswith("- "):
            have.append(pc.scalar(lines[end].lstrip()[2:]))
            end += 1
    if all(t in have for t in HOOK_TYPES):
        return lines
    found = have + [t for t in HOOK_TYPES if t not in have]
    return lines[:n] + [f"default_install_hook_types: [{', '.join(found)}]"] + lines[end:]


def _local_repo(text: str):
    return next((i for i in pc.items(text.splitlines())
                 if pc.scalar(i.keys.get("repo", "")) == "local" and "hooks" in i.keys), None)


def _add_tollgate(lines: list, hook: dict) -> list:
    """The lines with the hook `tollgate` in place: in place of the old one, first in the
    local repo, or in a new local repo before the other repos."""
    text = "\n".join(lines)
    old = pc.find(text, "tollgate")
    if old:
        return lines[:old.start] + hook_lines(hook, old.indent, old.column) + lines[old.end:]
    repo = _local_repo(text)
    if repo:
        at = repo.lines["hooks"]
        inside = [h for h in pc.hooks(text) if repo.start < h.start < repo.end]
        if inside:
            first = inside[0]
            return lines[:first.start] + hook_lines(hook, first.indent, first.column) + \
                lines[first.start:]
        _flat(lines[at], "the hooks of the local repo")
        indent = repo.column + 2
        head = lines[at].split(":", 1)[0] + ":"
        return lines[:at] + [head] + hook_lines(hook, indent, indent + 2) + lines[at + 1:]
    n = _top_key(lines, "repos")
    if n is None:
        return lines + ["repos:", "- repo: local", "  hooks:"] + hook_lines(hook)
    repos = [i for i in pc.items(text.splitlines()) if "repo" in i.keys and i.start > n]
    indent = repos[0].indent if repos else 0
    column = repos[0].column if repos else 2
    block = [f"{' ' * indent}-{' ' * (column - indent - 1)}repo: local",
             f"{' ' * column}hooks:"] + hook_lines(hook, column, column + 2)
    if repos:
        return lines[:repos[0].start] + block + lines[repos[0].start:]
    _flat(lines[n], "repos")
    return lines[:n] + ["repos:"] + block + lines[n + 1:]


def _flat(line: str, what: str) -> None:
    """Refuse a list on one line, other than [], that the block style would replace."""
    value = pc.scalar(line.split(":", 1)[1])
    if value and value != "[]":
        raise PrecommitError(f"{CONFIG} writes {what} on one line. Write them as a block "
                             "list, one item on each line, then run init again.")


def update(text: str, root: Path, moved: list) -> str:
    """The config with Tollgate's header and the hook `tollgate` in place, the hooks of an
    older Tollgate removed, and each hook in moved added once, after the hook `tollgate`.
    Every other line stays as it is."""
    lines = text.splitlines()
    while lines and (lines[0] in OLD_HEADER or lines[0] in HEADER):
        lines.pop(0)
    lines = HEADER + lines
    for old in reversed([h for h in pc.hooks("\n".join(lines))
                         if pc.scalar(h.keys["id"]).startswith(RETIRED_PREFIX)]):
        del lines[old.start:old.end]
    lines = _install_types(lines)
    lines = _add_tollgate(lines, tollgatehook_lines(root))
    have = pc.hook_ids("\n".join(lines))
    placed = "tollgate"
    for hook in [h for h in moved if h["id"] not in have]:
        last = pc.find("\n".join(lines), placed)
        lines = lines[:last.end] + hook_lines(hook, last.indent, last.column) + lines[last.end:]
        placed = hook["id"]
    return "\n".join(lines) + "\n"


def write(project: str = ".") -> list:
    """Copy the checks, write the hook `tollgate` and the moved checks into the config, and
    name the hooks in the settings. Return the paths that changed."""
    root = Path(project)
    path = root / SETTINGS
    settings = json.loads(path.read_text()) if path.exists() else {}
    changed = []
    own = is_tollgate(root)
    for name in SCRIPTS:
        target = root / CHECKS_DIR / name
        if own:
            # The checks run from setup/, so a copy in .tollgate/checks/ is a second truth.
            if target.exists():
                target.unlink()
                changed.append(f"{CHECKS_DIR}/{name}")
            continue
        data = (HERE / name).read_bytes()
        if not target.exists() or target.read_bytes() != data:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / name, target)
            changed.append(f"{CHECKS_DIR}/{name}")
    for name in RETIRED:
        old = root / CHECKS_DIR / name
        if old.exists():
            old.unlink()
            changed.append(f"{CHECKS_DIR}/{name}")
    config = root / CONFIG
    checks, moved = migrate_checks(settings.get("checks", {}))
    if config.exists():
        old = config.read_text()
        text = update(old, root, moved)
    else:
        old, text = None, render(settings, root)
    if text != old:
        config.write_text(text)
        changed.append(CONFIG)
    if moved:
        settings["checks"] = checks
        path.write_text(json.dumps(settings, indent=2) + "\n")
        changed.append(SETTINGS)
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="precommit", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=".")
    args = parser.parse_args(argv)
    try:
        changed = write(args.project)
    except (PrecommitError, OSError, ValueError) as err:
        print(f"precommit: {err}", file=sys.stderr)
        return 1
    for path in changed:
        print(f"changed {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
