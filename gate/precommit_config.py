"""Read the hooks of a project's .pre-commit-config.yaml, with the standard library only.

Tollgate needs no YAML library, so this reads the block style that pre-commit configs
use: a list item starts with `- `, and its keys are on the lines below it, one column
right of the dash. It knows what Tollgate needs: each hook's id and stages, the
top-level `default_stages`, and where each list item starts and ends, so that
setup.precommit can change one hook and keep every other line as it is.
"""

import json
import re
from dataclasses import dataclass, field

CONFIG = ".pre-commit-config.yaml"
# The stage names of pre-commit before version 3, and the names it uses now.
OLD_STAGES = {"commit": "pre-commit", "push": "pre-push", "merge-commit": "pre-merge-commit"}
# The stage the gate runs a hook at, when the hook has more than one.
PREFERRED = ("pre-push", "pre-commit", "pre-merge-commit", "manual")
KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):(?:\s+(?P<value>.*))?$")


@dataclass
class Item:
    """One list item of the config: its lines are lines[start:end]."""
    start: int
    end: int
    indent: int        # the column of the dash
    column: int        # the column of the item's keys
    keys: dict = field(default_factory=dict)   # key -> the value on the key's own line
    lines: dict = field(default_factory=dict)  # key -> the index of the key's line


def _meaningful(line: str) -> bool:
    text = line.strip()
    return bool(text) and not text.startswith("#")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def scalar(value: str) -> str:
    """The text of a YAML scalar on one line, without quotes or a trailing comment."""
    value = value.strip()
    if value.startswith("#"):
        return ""
    if value.startswith('"'):
        end = value.find('"', 1)
        while end > 0 and value[end - 1] == "\\":
            end = value.find('"', end + 1)
        try:
            return json.loads(value[:end + 1]) if end > 0 else value
        except ValueError:
            return value[1:end]
    if value.startswith("'"):
        end = value.find("'", 1)
        while end > 0 and value[end + 1:end + 2] == "'":
            end = value.find("'", end + 2)
        return value[1:end].replace("''", "'") if end > 0 else value
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def flow_list(value: str) -> list:
    """The items of `[a, "b"]`. A plain scalar counts as a list of one item."""
    value = value.strip()
    if not value.startswith("[") or "]" not in value:
        return [scalar(value)] if scalar(value) else []
    return [scalar(part) for part in value[1:value.rfind("]")].split(",") if part.strip()]


def items(lines: list) -> list:
    """Every list item of the config, at any depth, in order."""
    found = []
    for i, line in enumerate(lines):
        text = line.lstrip(" ")
        if not (text.startswith("- ") or text.rstrip() == "-"):
            continue
        indent = _indent(line)
        end = i + 1
        while end < len(lines) and not (_meaningful(lines[end]) and _indent(lines[end]) <= indent):
            end += 1
        while end > i + 1 and not _meaningful(lines[end - 1]):
            end -= 1   # blank lines and comments after an item belong to what comes next
        rest = text[1:]
        column = indent + 1 + (len(rest) - len(rest.lstrip(" ")))
        item = Item(i, end, indent, column)
        first = KEY.match(rest.strip())
        if first:
            item.keys[first["key"]] = first["value"] or ""
            item.lines[first["key"]] = i
        for j in range(i + 1, end):
            if _meaningful(lines[j]) and _indent(lines[j]) == column:
                match = KEY.match(lines[j].strip())
                if match and match["key"] not in item.keys:
                    item.keys[match["key"]] = match["value"] or ""
                    item.lines[match["key"]] = j
        found.append(item)
    return found


def _list_value(lines: list, index: int, value: str, column: int, end: int) -> list:
    """The items of a list whose key is on lines[index]: in flow style on the same line,
    or in block style on the lines below it."""
    if value.strip() and not value.strip().startswith("#"):
        return flow_list(value)
    out = []
    for j in range(index + 1, end):
        line = lines[j]
        if not _meaningful(line):
            continue
        text = line.lstrip(" ")
        if _indent(line) < column or not text.startswith("- "):
            break
        out.append(scalar(text[2:]))
    return out


def hooks(text: str) -> list:
    """The hook items of the config: each list item with an id."""
    return [i for i in items(text.splitlines()) if "id" in i.keys]


def hook_ids(text: str) -> list:
    return [scalar(i.keys["id"]) for i in hooks(text)]


def find(text: str, hook_id: str) -> Item | None:
    """The hook item with this id, or None."""
    return next((i for i in hooks(text) if scalar(i.keys["id"]) == hook_id), None)


def default_stages(text: str) -> list:
    lines = text.splitlines()
    for n, line in enumerate(lines):
        match = KEY.match(line) if _indent(line) == 0 else None
        if match and match["key"] == "default_stages":
            return [OLD_STAGES.get(s, s) for s in
                    _list_value(lines, n, match["value"] or "", 0, len(lines))]
    return []


def stages(text: str, hook_id: str) -> list | None:
    """The stages a hook runs at, or None when the config has no hook with this id."""
    item = find(text, hook_id)
    if item is None:
        return None
    lines = text.splitlines()
    if "stages" in item.keys:
        found = _list_value(lines, item.lines["stages"], item.keys["stages"], item.column,
                            item.end)
    else:
        found = default_stages(text)
    return [OLD_STAGES.get(s, s) for s in found]


def run_stage(text: str, hook_id: str) -> str | None:
    """The stage the gate runs a hook at, with `pre-commit run --hook-stage`: pre-push
    when the hook runs there, then the other stages in PREFERRED order. A hook that names
    no stage runs at every stage, so pre-commit. None when the hook is not in the config."""
    found = stages(text, hook_id)
    if found is None:
        return None
    for stage in PREFERRED:
        if stage in found:
            return stage
    return found[0] if found else "pre-commit"
