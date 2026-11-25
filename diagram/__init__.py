"""Diagrams as SVG, in a light and a dark theme, that people can read.

The kinds, chosen by "type" in the spec:

- "flow" (the default): a flat blueprint flowchart. Steps in the standard
  flowchart shapes, arrows, groups, AWS icons. Format: diagram/flow.py.
- "sequence": a UML sequence diagram. Participants across the top, messages
  down the page in time order. Format: diagram/sequence.py.
- "state": a UML state machine. States, and the events that move one thing
  between them. Format: diagram/state.py.
- "c4": a C4 diagram of software architecture, at one of five levels:
  context, container, component, dynamic, or deployment. Built on the flow.
  Format: diagram/c4.py.
- "usecase": a UML use case diagram. Actors, the use cases of one system, and
  the links between them. Built on the flow. Format: diagram/usecase.py.
- "class" and "er": a UML class diagram, or an entity relationship diagram
  with crow's foot ends. Format: diagram/model.py.
- "scene": an isometric picture of places and things, with lanes between
  them and one change that travels. Format below.

    from diagram import draw
    svg = draw(spec, "light")      # or "dark"

    python3 -m diagram build docs/diagrams    # every spec in docs/diagrams/src/
    python3 -m diagram build docs/diagrams --check

A scene spec:

    {"type": "scene", "title": "...", "desc": "...",
     "size": [1120, 640], "origin": [560, 330], "scale": 0.8,
     "caption": ["Big title", "one line under it"],
     "zones":   [{"at": [x0, y0, x1, y1], "kind": "ai", "z": 0, "height": 8}],
     "packets": true,
     "lanes":   [{"path": [[x, y], [x, y]], "label": "the change", "at": 0.5,
                  "kind": "you" | "ai" | "server" | "check" | "advisor" | "neutral",
                  "tone": "pass" | "fail", "side": true}],
     "objects": [{"type": "room" | "gate" | "server" | "vault" | "papers" | "laptop" |
                          "board" | "house" | "database" | "pedestal" | "aws" | "wall" |
                          "person" | "external" | "building" | "container" | "queue" |
                          "cloud" | "component",
                  "at": [x, y], "z": 0, "kind": "server", "means": "the gate", ...}],
     "badges":  [{"at": [x, y, z], "icon": "lock", "kind": "server"}],
     "labels":  [{"at": [x, y, z], "head": "Main", "sub": ["line", "line"],
                  "anchor": "start" | "middle" | "end", "halo": true,
                  "pin": [x, y, z], "n": 1, "kind": "ai", "drop": 60, "route": "level"}],
     "note":    {"n": 8, "head": "Always", "line": "One short line.", "kind": "neutral"},
     "ticket":  {"legs": [{"path": [[x, y], ...], "tone": "fail", "wait": 0.9}],
                 "lift": 6},
     "callouts": [{"n": 1, "head": "Plan first", "line": "One short sentence or two.",
                   "to": [x, y, z], "side": "left" | "right" | "bottom", "kind": "ai"}]}

"packets": true puts one small dot on every lane, each in its lane's color, so
all the lanes show their direction at once; the ticket stays the one dot that
tells the order. A lane's "kind" sets its color and arrowhead, as for a label;
a "tone" wins over a kind, and a lane with neither keeps the old look.
Ground units: x runs down-right on the page, y runs down-left, z runs up.
"gate" takes "arm_to" (where the barrier ends) and "axis" ("x" or "y");
"pedestal" takes "icon"; "aws" takes "aws" (a service name); "wall" takes "to".
"person" is someone who uses the system, in the color of its kind. "external" is
a system that is not ours: a gray building, gray whatever its kind, with an
optional "size". A person, your system in a zone, and external systems around
it, with lanes for what flows, draw a C4 system context as a scene.
"building" is a system of ours, in its kind's color; "container" a box with a
lid and a door; "queue" a pipe on its side; "cloud" a cloud tied to a ring on
the ground; "component" a small block with the tabs of a UML component.
A zone with "z" stands that high, "height" thick: put one on another to make
a platform. An object with "z" stands that high, on a platform. A badge is an
icon in a ring, floating over a point. A lane's path may take [x, y, z]
points, and its label a line break for a second line. A label with "halo" has
a rim in the page's color, to stay clear over a line. A c4 spec with
"style": "isometric" is drawn as a scene like this: see diagram/c4.py.
"lift" names the ticket leg during which the gate's barrier is up.

A label with "pin" is tied to its part: a flat ring on the point "pin" names,
and a stem straight up or down from it, with one rounded turn, level to the
label. Place the label with "at", or with "drop" to put it that many pixels
under the pin, its words to the right of a straight stem. "route": "level"
sends the stem level first, then up or down: use it when a line straight up or
down would cross the part's icon or its body. Put the pin at the center of the
part's top. "n" puts a number
where the stem ends, and the numbered rings pulse in order. "kind" sets the
color. "note" is one numbered line under the caption, for what holds for the
whole picture.

Callouts are numbered labels beside the scene. The page widens by a column for
each side that has them, and grows by a row for each bottom one. A dotted
leader runs from each number to a small ring on the point "to" names; a
bottom callout sits centered under the scene, with no leader. Number them
clockwise: the left column reads upward, the right column downward, then the
bottom. A line wraps to at most two lines in its column; shorten a longer one.
"kind" sets the color.
"""

import importlib

# Every kind of diagram, by its "type" in the spec: the module that draws it, and
# what the format guide calls it, in the order the guide shows them. A new kind
# needs one line here and a module with draw(spec, theme) and its format on top.
KINDS = {
    "flow": ("flow", "a flow"),
    "sequence": ("sequence", "a sequence diagram"),
    "state": ("state", "a state machine"),
    "c4": ("c4", "a C4 diagram"),
    "usecase": ("usecase", "a use case diagram"),
    "class": ("model", "a class or ER diagram"),
    "er": ("model", "a class or ER diagram"),
    "scene": ("scene", "a scene"),
}


def module_of(kind: str):
    """The module that draws a kind, imported on first use."""
    return importlib.import_module(f"diagram.{KINDS[kind][0]}")


def draw(spec: dict, theme: str) -> str:
    kind = spec.get("type", "flow")
    if kind not in KINDS:
        names = list(KINDS)
        raise ValueError(f"no diagram type '{kind}'; use {', '.join(names[:-1])}, "
                         f"or {names[-1]}")
    return module_of(kind).draw(spec, theme)
