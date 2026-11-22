"""Diagrams as SVG, in a light and a dark theme, that people can read.

Two kinds, chosen by "type" in the spec:

- "flow" (the default): a flat blueprint flowchart. Steps in the standard
  flowchart shapes, arrows, groups, AWS icons. Format: diagram/flow.py.
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
                          "board" | "house" | "database" | "pedestal" | "aws" | "wall",
                  "at": [x, y], "kind": "server", ...}],
     "labels":  [{"at": [x, y, z], "head": "Main", "sub": ["line", "line"],
                  "anchor": "start" | "middle" | "end"}],
     "ticket":  {"legs": [{"path": [[x, y], ...], "tone": "fail", "wait": 0.9}],
                 "lift": 6},
     "callouts": [{"n": 1, "head": "Plan first", "line": "One short sentence or two.",
                   "to": [x, y, z], "side": "left" | "right" | "bottom", "kind": "ai"}]}

Ground units: x runs down-right on the page, y runs down-left, z runs up.
"gate" takes "arm_to" (where the barrier ends) and "axis" ("x" or "y");
"pedestal" takes "icon"; "aws" takes "aws" (a service name); "wall" takes "to".
"lift" names the ticket leg during which the gate's barrier is up.

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
    if spec.get("type") == "scene":
        return scene.from_spec(spec, theme)
    return flow.draw(spec, theme)
