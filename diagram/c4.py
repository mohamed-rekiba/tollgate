"""Draw a C4 diagram as SVG, in a light and a dark theme: built on the flow.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"type": "c4",
     "level": "context" | "container" | "component" | "dynamic" | "deployment",
     "title": "Tollgate",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "names": {"server": "Tollgate"},
     "boundaries": [{"id": "tg", "name": "Tollgate", "type": "Software System",
                     "parent": "outer", "kind": "server"}],
     "elements": [{"id": "you", "type": "person" | "system" | "container" | "database" |
                                       "queue" | "component" | "node",
                   "name": "You", "tech": "Python", "description": "One short line",
                   "external": true, "stereotype": "device", "col": 0, "row": 0,
                   "parent": "tg", "kind": "you" | "ai" | "server" | "check" | "advisor",
                   "icon": "lock"}],
     "relations": [{"from": "you", "to": "tg", "label": "Gives a task", "tech": "a skill",
                    "tone": "pass" | "fail", "dashed": true,
                    "loop": "left" | "right" | "above" | "below",
                    "route": "vhv" | "vh" | "hv"}]}

The design follows C4 (c4model.com), drawn in Tollgate's style:
- "level" says which C4 diagram this is. It names the diagram, as in
  "Container diagram for Tollgate", over its top left and in its title for a
  screen reader, and it decides which elements may appear:
  - "context": people and software systems.
  - "container": people, software systems, and containers: "container",
    "database", "queue".
  - "component": all of those, and components.
  - "dynamic": the same as "component". The arrows are numbered in the order
    they are listed, "1. ", "2. ", "3. ": list them in the order they happen.
  - "deployment": a UML deployment diagram. Nodes, and the software systems
    and containers that run on them. No people.
- An element shows its name in bold, its type in brackets, and its
  description, wrapped to short lines. The type comes from "type" and "tech":
  "[Person]", "[Software System]", "[Container: Python]",
  "[Component: Python]". A "node" shows its "stereotype" in guillemets, such
  as «device», or "[Node]".
- The shape follows the type: a "person" is a head over a box with round
  shoulders, a "database" is a cylinder, a "queue" is a pipe on its side, a
  "node" is a box in three dimensions, and the rest are boxes.
- "external": true marks an element outside the thing the diagram is about.
  It is gray, and its type says "External", as in "[External System]". It
  takes no "kind".
- "kind" says who acts, as in a flow. It sets the color, the icon, and the
  small label over the name; "names" renames those labels. By default a person
  is "you" and every other element "server". "icon" picks another icon.
- Elements sit on a grid of "col" and "row", as in a flow.
- "boundaries" are dashed boxes around the elements whose "parent" names them,
  with the name in bold and the type in brackets, as in
  "Tollgate [Software System]". A boundary may sit in another one: give it a
  "parent" too. At the deployment level a boundary is a node that holds
  others: a box in three dimensions with its type as a stereotype, as in
  "Your machine «device»", nested as deep as you need.
- A relation is an arrow with a label: what happens, then on a second line
  how, in brackets, from "tech". Every relation needs a "label". "tone",
  "dashed", "loop", and "route" work as in a flow.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

import textwrap

from diagram import flow
from diagram.icons import ICONS

LEVELS = {
    "context": ("System Context", ("person", "system")),
    "container": ("Container", ("person", "system", "container", "database", "queue")),
    "component": ("Component", ("person", "system", "container", "database", "queue",
                                "component")),
    "dynamic": ("Dynamic", ("person", "system", "container", "database", "queue",
                            "component")),
    "deployment": ("Deployment", ("node", "system", "container", "database", "queue")),
}
TYPES = ("person", "system", "container", "database", "queue", "component", "node")
SHAPE = {"person": "person", "database": "data", "queue": "queue", "node": "node"}
ICON = {"person": "person", "database": "database", "queue": "queue", "node": "server"}
WRAP = 24   # characters on a line of a description


def type_line(e):
    """The element's type in brackets, as C4 writes it."""
    kind, tech = e["type"], e.get("tech")
    if kind == "node" and e.get("stereotype"):
        return f"«{e['stereotype']}»"
    word = {"person": "Person", "system": "System" if e.get("external") else "Software System",
            "container": "Container", "database": "Container", "queue": "Container",
            "component": "Component", "node": "Node"}[kind]
    if e.get("external"):
        word = f"External {word}"
    return f"[{word}: {tech}]" if tech else f"[{word}]"


def node_of(e):
    """One element as a node of the flow."""
    lines = [e["name"], type_line(e)]
    for part in (e.get("description") or "").split("\n"):
        lines += textwrap.wrap(part, WRAP)
    out = {"id": e["id"], "text": "\n".join(lines), "col": e["col"], "row": e["row"],
           "shape": SHAPE.get(e["type"], "step")}
    if e.get("external"):
        out["kind"] = "neutral"
        out["icon"] = e.get("icon") or ICON.get(e["type"], "globe")
    else:
        out["kind"] = e.get("kind") or ("you" if e["type"] == "person" else "server")
        if e.get("icon") or e["type"] in ICON:
            out["icon"] = e.get("icon") or ICON[e["type"]]
    return out


def label_of(r, n, dynamic):
    what = f"{n}. {r['label']}" if dynamic else r["label"]
    return f"{what}\n[{r['tech']}]" if r.get("tech") else what


def depth(b, by_id):
    n = 0
    while b.get("parent"):
        b, n = by_id[b["parent"]], n + 1
    return n


def groups(spec):
    """The boundaries as groups of the flow, the outer ones first."""
    bounds = spec.get("boundaries", [])
    by_id = {b["id"]: b for b in bounds}

    def inside(bid):
        """Every element in this boundary, or in one inside it."""
        mine = [e["id"] for e in spec["elements"] if e.get("parent") == bid]
        for b in bounds:
            if b.get("parent") == bid:
                mine += inside(b["id"])
        return mine

    style = "node" if spec["level"] == "deployment" else "boundary"
    out = []
    cells = {e["id"]: (e["col"], e["row"]) for e in spec["elements"]}
    for b in sorted(bounds, key=lambda b: depth(b, by_id)):
        nodes = inside(b["id"])
        if not nodes:
            raise ValueError(f"boundary '{b['id']}' holds no element")
        cols = [cells[n][0] for n in nodes]
        rows = [cells[n][1] for n in nodes]
        for other, (c, r) in cells.items():
            if other not in nodes and min(cols) <= c <= max(cols) and min(rows) <= r <= max(rows):
                raise ValueError(f"element '{other}' sits in the box of boundary '{b['id']}' but "
                                 "is not inside it: move it to another col or row")
        g = {"label": b["name"], "nodes": nodes, "style": style,
             "kind": b.get("kind", "neutral")}
        if b.get("type"):
            g["type"] = b["type"]
        out.append(g)
    return out


def to_flow(spec):
    """The C4 spec as a flow spec."""
    check(spec)
    prefix, _ = LEVELS[spec["level"]]
    title = f"{prefix} diagram for {spec['title']}"
    dynamic = spec["level"] == "dynamic"
    edges = []
    for n, r in enumerate(spec.get("relations", []), start=1):
        e = {"from": r["from"], "to": r["to"], "label": label_of(r, n, dynamic)}
        e.update({k: r[k] for k in ("tone", "dashed", "loop", "route") if k in r})
        edges.append(e)
    out = {"title": title, "heading": title, "desc": spec["desc"],
           "nodes": [node_of(e) for e in spec["elements"]], "edges": edges,
           "groups": groups(spec)}
    if spec.get("names"):
        out["names"] = spec["names"]
    return out


def draw(spec, theme):
    return flow.draw(to_flow(spec), theme)


def whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_types(spec):
    """Every part of the spec has the type the drawing needs, or a plain message
    says which one does not. The error is a ValueError, as for any bad spec."""
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")  # noqa: TRY004
    for key in ("title", "desc", "level"):
        if not isinstance(spec.get(key, ""), str):
            raise ValueError(f"the diagram's '{key}' must be text")  # noqa: TRY004
    names = spec.get("names", {})
    if not isinstance(names, dict) or not all(isinstance(v, str) for v in names.values()):
        raise ValueError("'names' must be an object of kind: label, such as "
                         '{"server": "Tollgate"}')
    for part, texts, flags in (
            ("elements", ("id", "type", "name", "tech", "description", "parent", "kind", "icon",
                          "stereotype"), ("external",)),
            ("boundaries", ("id", "name", "type", "parent", "kind"), ()),
            ("relations", ("from", "to", "label", "tech", "tone", "loop", "route"), ("dashed",))):
        items = spec.get(part, [])
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ValueError(f"'{part}' must be a list of objects")
        for i, item in enumerate(items):
            for key in texts:
                if key in item and not isinstance(item[key], str):
                    raise ValueError(f"{part[:-1]} {i}: '{key}' must be text")
            for key in flags:
                if key in item and not isinstance(item[key], bool):
                    raise ValueError(f"{part[:-1]} {i}: '{key}' must be true or false")
            if part == "elements" and not (whole(item.get("col")) and whole(item.get("row"))):
                raise ValueError(f"element {i} needs a whole number for 'col' and 'row'")


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    check_types(spec)
    for key in ("title", "desc"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    level = spec.get("level")
    if level not in LEVELS:
        raise ValueError(f"the level must be one of {', '.join(LEVELS)}")
    elements = spec.get("elements")
    if not elements:
        raise ValueError("the diagram has no elements")
    bounds = {b.get("id"): b for b in spec.get("boundaries", [])}
    for b in bounds.values():
        if not b.get("id") or not b.get("name"):
            raise ValueError("every boundary needs an 'id' and a 'name'")
        seen, at = {b["id"]}, b
        while at.get("parent"):
            if at["parent"] not in bounds:
                raise ValueError(f"boundary '{at['id']}' is inside '{at['parent']}', "
                                 "which is not a boundary")
            at = bounds[at["parent"]]
            if at["id"] in seen:
                raise ValueError(f"boundary '{b['id']}' ends up inside itself")
            seen.add(at["id"])
    allowed = LEVELS[level][1]
    ids = set()
    for e in elements:
        eid = e.get("id")
        if not eid:
            raise ValueError("every element needs an 'id'")
        if eid in ids or eid in bounds:
            raise ValueError(f"two elements or boundaries share the id '{eid}'")
        ids.add(eid)
        if e.get("type") not in TYPES:
            raise ValueError(f"element '{eid}': type must be one of {', '.join(TYPES)}")
        if e["type"] not in allowed:
            raise ValueError(f"a {level} diagram cannot hold a {e['type']} ('{eid}'); "
                             f"it holds {', '.join(allowed)}")
        if not e.get("name"):
            raise ValueError(f"element '{eid}' needs a 'name'")
        if e.get("external") and e.get("kind"):
            raise ValueError(f"element '{eid}' is external, so it is gray: drop its kind")
        if e.get("parent") and e["parent"] not in bounds:
            raise ValueError(f"element '{eid}' is inside '{e['parent']}', which is not a boundary")
        if e.get("icon") and e["icon"] not in ICONS:
            raise ValueError(f"element '{eid}': no icon named '{e['icon']}'")
    for r in spec.get("relations", []):
        for end in ("from", "to"):
            if r.get(end) not in ids:
                raise ValueError(f"a relation {end} '{r.get(end)}', which is not an element")
        if not r.get("label"):
            raise ValueError(f"the relation {r['from']} -> {r['to']} needs a 'label': "
                             "what happens")
