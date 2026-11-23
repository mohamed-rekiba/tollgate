"""Diagrams as SVG, in a light and a dark theme, that people can read.

Four kinds, chosen by "type" in the spec:

- "flow" (the default): a flat blueprint flowchart. Steps in the standard
  flowchart shapes, arrows, groups, AWS icons. Format: diagram/flow.py.
- "sequence": a UML sequence diagram. Participants across the top, messages
  down the page in time order. Format: diagram/sequence.py.
- "state": a UML state machine. States, and the events that move one thing
  between them. Format: diagram/state.py.
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
     "zones":   [{"at": [x0, y0, x1, y1], "kind": "ai"}],
     "lanes":   [{"path": [[x, y], [x, y]], "label": "the change", "at": 0.5,
                  "tone": "pass" | "fail", "side": true}],
     "objects": [{"type": "room" | "gate" | "server" | "vault" | "papers" | "laptop" |
                          "board" | "house" | "database" | "pedestal" | "aws" | "wall" |
                          "person" | "external",
                  "at": [x, y], "kind": "server", ...}],
     "labels":  [{"at": [x, y, z], "head": "Main", "sub": ["line", "line"],
                  "anchor": "start" | "middle" | "end",
                  "pin": [x, y, z], "n": 1, "kind": "ai", "drop": 60, "route": "level"}],
     "note":    {"n": 8, "head": "Always", "line": "One short line.", "kind": "neutral"},
     "ticket":  {"legs": [{"path": [[x, y], ...], "tone": "fail", "wait": 0.9}],
                 "lift": 6},
     "callouts": [{"n": 1, "head": "Plan first", "line": "One short sentence or two.",
                   "to": [x, y, z], "side": "left" | "right" | "bottom", "kind": "ai"}]}

Ground units: x runs down-right on the page, y runs down-left, z runs up.
"gate" takes "arm_to" (where the barrier ends) and "axis" ("x" or "y");
"pedestal" takes "icon"; "aws" takes "aws" (a service name); "wall" takes "to".
"person" is someone who uses the system, in the color of its kind. "external" is
a system that is not ours: a gray building, gray whatever its kind, with an
optional "size". A person, your system in a zone, and external systems around
it, with lanes for what flows, draw a C4 system context as a scene.
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

from diagram import flow, scene


def draw(spec: dict, theme: str) -> str:
    kind = spec.get("type", "flow")
    if kind == "scene":
        return scene.from_spec(spec, theme)
    if kind == "sequence":
        from diagram import sequence
        return sequence.draw(spec, theme)
    if kind == "state":
        from diagram import state
        return state.draw(spec, theme)
    if kind != "flow":
        raise ValueError(f"no diagram type '{kind}'; use flow, sequence, state, or scene")
    return flow.draw(spec, theme)
