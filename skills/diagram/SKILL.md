---
name: diagram
description: Draw a diagram for this project as an SVG file, light and dark, readable by a screen reader - a flat blueprint flow, an isometric scene, a diagram drawn from the code, or an AWS architecture with the official AWS icons. Use whenever a doc, README, plan, or report needs a diagram, a flowchart, an architecture picture, or an icon. Never use Mermaid or an image of text.
---

# Draw a diagram

Every diagram is SVG, drawn by code in this repo, in a light and a dark file. `tests/test_diagrams.py` fails on a Mermaid block, on an SVG that breaks the rules below, and on a drawing that no longer matches its source.

## Pick the kind

| The diagram shows | Kind | Where it lives |
| --- | --- | --- |
| Steps, a flow, a sequence, choices | Flat blueprint | a spec in `docs/diagrams/src/<name>.json` |
| The big picture: places, who holds what, how parts sit together | Isometric scene | a function in `docs/diagrams/scenes.py` |
| Something the code already says, like the jobs of a workflow | From the code | a function in `docs/diagrams/build.py` (`GENERATED`) |
| AWS architecture | Flat blueprint with `aws` nodes and groups | a spec, as for a flat one |
| A banner or one-off art | Art | a module like `docs/diagrams/hero.py` (`ART`) |

One diagram, one idea. Over about ten boxes, split it.

## A flat blueprint diagram

1. Write the spec. The full format is at the top of `driver/diagram.py`.
   - `title`: what it is, in a few words. `desc`: what it shows, in one or two sentences. A screen reader reads `desc` aloud, so write the meaning, not the shapes.
   - `nodes`: boxes on a grid of `col` and `row`. `text` is a short title, then at most three short lines, split by `\n`.
   - `kind` says who acts: `you`, `ai`, `server`, `check`, `advisor`. It sets the color, the icon, and the label over the title. Use the same kind for the same actor everywhere. With no kind, a box is neutral.
   - `icon` picks another icon by name (see the sheet in `docs/diagrams/README.md`). `step` adds STEP n. `tag` replaces the label.
   - `edges`: `tone` is `pass` or `fail`, always with a `label`. `dashed` is a side path. `loop` (left, right, above, below) is an arrow that goes back. `route` (vhv, vh, hv) picks the bends.
   - `groups`: a border around nodes, for a place or a repeat ("For each ticket"). Inner groups hold a subset of the outer one's nodes.
   - `ticket`: one dot that travels a path of edges. Use it once, in a diagram about a change moving through.
2. Run `python3 docs/diagrams/build.py`.
3. Look at both files. Render them in a browser, or with `rsvg-convert -z 1.3 <file>.svg -o /tmp/x.png`, and read the PNG. Fix any label that covers a box or a line, often by moving a node or picking another `route`. Keep it under about 1000 pixels wide.

## An isometric scene

Use the kit in `docs/diagrams/iso.py`: `platform`, `room`, `booth`, `server`, `vault`, `papers`, `laptop`, `board`, `house`, `badge` (an icon over an object), `lane` (a path with moving dots), `text`, and `leg` with `ticket` for a travelling change.

- Ground units: x runs down-right on the page, y runs down-left, z runs up.
- Draw lanes first, then objects from back to front (smaller x + y first), then labels.
- Put each label beside its object, not on another one. Check it rendered, in both themes, at the moment the motion matters.
- Register the scene in `ART` in `build.py`.

## AWS architecture

1. Fetch the official icons once: `python3 -m setup.aws_icons`. They go to a cache on this machine, never into git. AWS allows its icons in architecture diagrams, unchanged.
2. In the spec, give a node `"aws": "<service>"`, such as `s3`, `lambda`, `dynamodb`, `apigw`, or a name from the package. It draws the AWS icon with its name under it.
3. Give a group `"aws": "<group>"`: `cloud`, `account`, `region`, `az`, `vpc`, `public subnet`, `private subnet`, `security group`, `auto scaling`, `data center`. It draws AWS's border, in the group's own color, with its group icon in the corner. Nest them in AWS's order: Cloud, Region, VPC, Availability Zone, subnet.
4. Do not crop, recolor, rotate, or redraw an AWS icon. If the package has no icon for a thing, use a Tollgate icon or a plain box.

## Put it in the markdown

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/<name>-dark.svg">
  <img alt="<the title>" src="docs/diagrams/<name>.svg">
</picture>
```

Write the paths relative to the markdown file. Then run `python3 -m pytest tests/test_diagrams.py`, and commit the source and both SVG files together.

## Rules

The test checks these on every SVG in the repo.

- The root has `role="img"`, a `viewBox`, and `aria-labelledby` naming a `<title>` and a `<desc>`.
- Text is real `<text>`, never a path. No `<script>`, no `<foreignObject>`, no `<image>`, no event attributes, no external file or CSS.
- Text has a contrast of 4.5 to 1 on its fill, and lines 3 to 1 on the page, in both themes. The colors in `driver/diagram.py` meet this. Do not add colors outside them.
- Color means who acts, and only that. The label over each box says it in words too. A colored arrow always has a label.
- Motion shows direction only: moving dots, one travelling ticket, a barrier that lifts. All of it stops under `prefers-reduced-motion`.
- No `prefers-color-scheme` inside an SVG. Use the two files and the `picture` element.
- The background is a full square, so no corner shows through on a page of the other theme.
