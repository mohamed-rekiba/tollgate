"""Draw a UML use case diagram as SVG, in a light and a dark theme: built on the flow.

    from diagram import draw
    svg = draw(spec, "light")   # or "dark"

A spec is a dict, often read from JSON:

    {"type": "usecase",
     "title": "Short name of the diagram",
     "desc": "What it shows, in one or two sentences, for a screen reader.",
     "names": {"advisor": "Owner"},
     "system": "Tollgate",
     "actors": [{"id": "owner", "name": "Owner", "description": "One short line",
                 "col": 0, "row": 0,
                 "kind": "you" | "ai" | "server" | "check" | "advisor", "icon": "key"}],
     "cases": [{"id": "approve", "name": "Approve a change", "description": "One short line",
                "col": 1, "row": 0, "kind": "check", "icon": "key"}],
     "links": [{"from": "owner", "to": "approve",
                "type": "association" | "include" | "extend",
                "loop": "left" | "right" | "above" | "below",
                "route": "vhv" | "vh" | "hv"}]}

The design follows UML, drawn in Tollgate's style:
- An actor is a person: a head over a box with round shoulders, with its name
  and an optional short description. Put actors outside the system, in their
  own columns, to its left or right; an actor in the system's box is an error.
- A use case is an oval with its name, a goal in a few words, such as
  "Approve a change". Every use case sits inside the system's border, a plain
  box with "system" as its name in bold.
- "kind" says who acts, as in a flow: it sets the color, the icon, and the
  small label; "names" renames the labels. By default an actor is "you" and a
  use case "server".
- Actors and use cases sit on a grid of "col" and "row", as in a flow.
- A link of "type" "association", the default, joins an actor and a use case:
  a plain line with no head. "include" and "extend" join two use cases: a
  dashed arrow labeled «include» or «extend». "include" points from the use
  case to the one it always includes; "extend" points from the extra use case
  to the one it extends. "loop" and "route" work as in a flow.

The output is plain SVG: real text, a viewBox, role="img" with a title and a
description named by aria-labelledby, no scripts, and no external files.
"""

import textwrap

from diagram import flow

LINKS = ("association", "include", "extend")
WRAP = 22


def node_of(item, shape, kind):
    lines = [item["name"]]
    for part in (item.get("description") or "").split("\n"):
        lines += textwrap.wrap(part, WRAP)
    out = {"id": item["id"], "text": "\n".join(lines), "col": item["col"], "row": item["row"],
           "shape": shape, "kind": item.get("kind", kind)}
    if item.get("icon"):
        out["icon"] = item["icon"]
    return out


def to_flow(spec):
    """The use case spec as a flow spec."""
    check(spec)
    nodes = ([node_of(a, "person", "you") for a in spec.get("actors", [])]
             + [node_of(c, "oval", "server") for c in spec["cases"]])
    edges = []
    for link in spec.get("links", []):
        kind = link.get("type", "association")
        e = {"from": link["from"], "to": link["to"]}
        if kind == "association":
            e["arrow"] = False
        else:
            e.update(dashed=True, label=f"«{kind}»")
        e.update({k: link[k] for k in ("loop", "route") if k in link})
        edges.append(e)
    out = {"title": spec["title"], "desc": spec["desc"], "nodes": nodes, "edges": edges,
           "groups": [{"label": spec["system"], "style": "system",
                       "nodes": [c["id"] for c in spec["cases"]]}]}
    if spec.get("names"):
        out["names"] = spec["names"]
    if spec.get("packets"):
        out["packets"] = True
    return out


def draw(spec, theme):
    return flow.draw(to_flow(spec), theme)


def check_types(spec):
    """Every part of the spec has the type the drawing needs, or a plain message
    says which one does not. The error is a ValueError, as for any bad spec."""
    if not isinstance(spec, dict):
        raise ValueError("the spec must be an object")  # noqa: TRY004
    for key in ("title", "desc", "system"):
        if not isinstance(spec.get(key, ""), str):
            raise ValueError(f"the diagram's '{key}' must be text")  # noqa: TRY004
    names = spec.get("names", {})
    if not isinstance(names, dict) or not all(isinstance(v, str) for v in names.values()):
        raise ValueError("'names' must be an object of kind: label, such as "
                         '{"advisor": "Owner"}')
    for part, texts in (("actors", ("id", "name", "description", "kind", "icon")),
                        ("cases", ("id", "name", "description", "kind", "icon")),
                        ("links", ("from", "to", "type", "loop", "route"))):
        items = spec.get(part, [])
        if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
            raise ValueError(f"'{part}' must be a list of objects")
        for i, item in enumerate(items):
            for key in texts:
                if key in item and not isinstance(item[key], str):
                    raise ValueError(f"{part} {i}: '{key}' must be text")
            if part != "links" and not all(isinstance(item.get(k), int)
                                           and not isinstance(item.get(k), bool)
                                           for k in ("col", "row")):
                raise ValueError(f"{part} {i} needs a whole number for 'col' and 'row'")


def check(spec):
    """Stop with a plain message when a spec cannot be drawn."""
    check_types(spec)
    for key in ("title", "desc", "system"):
        if not spec.get(key):
            raise ValueError(f"the diagram needs a '{key}'")
    if not spec.get("cases"):
        raise ValueError("the diagram has no use cases")
    actors = {a.get("id") for a in spec.get("actors", [])}
    cases = {c.get("id") for c in spec["cases"]}
    for item in [*spec.get("actors", []), *spec["cases"]]:
        if not item.get("id") or not item.get("name"):
            raise ValueError("every actor and use case needs an 'id' and a 'name'")
    if actors & cases:
        raise ValueError(f"an actor and a use case share the id '{min(actors & cases)}'")
    cols = [c["col"] for c in spec["cases"]]
    rows = [c["row"] for c in spec["cases"]]
    for a in spec.get("actors", []):
        if min(cols) <= a["col"] <= max(cols) and min(rows) <= a["row"] <= max(rows):
            raise ValueError(f"actor '{a['id']}' sits in the box of the system "
                             f"'{spec['system']}': move it to another col or row")
    for link in spec.get("links", []):
        for end in ("from", "to"):
            if link.get(end) not in actors | cases:
                raise ValueError(f"a link {end} '{link.get(end)}', which is not an actor "
                                 "or a use case")
        kind = link.get("type", "association")
        if kind not in LINKS:
            raise ValueError(f"a link's type must be one of {', '.join(LINKS)}")
        ends = {link["from"] in cases, link["to"] in cases}
        if kind == "association" and ends != {True, False}:
            raise ValueError(f"the link {link['from']} -> {link['to']} is an association, "
                             "which joins an actor and a use case")
        if kind != "association" and ends != {True}:
            raise ValueError(f"the link {link['from']} -> {link['to']} is an {kind}, "
                             "which joins two use cases")
