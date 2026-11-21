---
name: diagram
description: Draw a diagram for this project as an SVG file, light and dark, readable by a screen reader. Use whenever a doc, README, plan, or report needs a diagram, a flowchart, or a picture of how parts connect. Never use Mermaid or an image of text.
---

# Draw a diagram

Every diagram in this project is an SVG file. A test fails on a Mermaid block in any markdown file.

## Steps

1. Write a spec in `docs/diagrams/src/<name>.json`. Use a short name in lowercase with dashes. The full format is at the top of `docs/diagrams/build.py`.
   - `title`: what the diagram is, in a few words.
   - `desc`: what it shows, in one or two sentences. A screen reader reads this aloud, so write the meaning, not the shapes.
   - `nodes`: each box sits on a grid of `col` and `row`. `text` is a short title, then one or two short lines under it, split by `\n`.
   - `kind` on a node says who acts: `you`, `ai`, `server`, `check`, or `advisor`. It sets the color and the small label over the title. Use the same kind for the same actor in every diagram. `step` adds STEP n. `tag` replaces the label, for a box that is not an actor, like TIER 1.
   - `edges`: an arrow from one node to another. `tone` is `pass` (green) or `fail` (red). Always add a `label` with a tone, so the meaning is not in color alone. `dashed` marks a path off the main one. `loop` (left, right, above, below) draws an arrow that goes back, in its own lane. `route` (vhv, vh, hv) picks the bends for an arrow across rows and columns.
2. Run `python3 docs/diagrams/build.py`. It writes `<name>.svg` and `<name>-dark.svg`.
3. Look at both files. Render them with `rsvg-convert -z 1.3 docs/diagrams/<name>.svg -o /tmp/<name>.png` (and the `-dark` file) and read the PNGs. Fix any label that covers a box or a line, often by moving a node or picking another `route`. Keep the diagram under about 1000 pixels wide, so its text stays readable on GitHub.
4. Put it in the markdown with a `picture` element, so GitHub shows the dark file in dark mode:

   ```html
   <picture>
     <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/<name>-dark.svg">
     <img alt="<the title>" src="docs/diagrams/<name>.svg">
   </picture>
   ```

   Write the paths relative to the markdown file.
5. Run `python3 -m pytest tests/test_diagrams.py`. Commit the spec and both SVG files together.

## Rules

The test checks each of these on every SVG file in the repo.

- One diagram, one idea. Over about ten boxes, split it in two.
- Text in a box is plain words, the same words the docs use. A title of a few words, then at most three short lines.
- Color means who acts, and only that. The label over the title says the same in words.
- The root has `role="img"`, a `viewBox`, and `aria-labelledby` naming a `<title>` and a `<desc>`. Screen readers need all four.
- Text is real `<text>`, never a path. Search and copy then work.
- No `<script>`, no `<foreignObject>`, no event attributes, no external file. GitHub strips them, and they are a risk.
- Text has a contrast of 4.5 to 1 or more on its fill, and lines 3 to 1 or more on the page, in both themes. The colors in `build.py` meet this. Do not change them without checking.
- Do not rely on color alone. A colored arrow has a label, a side path has long dashes and the main path has dots, and each box names its actor.
- Motion shows direction only. The arrows are dotted and the dots move the way they point, by CSS in the SVG. Every animation stops under `prefers-reduced-motion`. No other motion.
- Do not put `prefers-color-scheme` inside the SVG. Browsers ignore it when the SVG is an image. Use the two files and the `picture` element.

## When the generator cannot draw it

For a picture the grid cannot hold, write the SVG by hand in `docs/diagrams/`, with a `-dark.svg` twin. It must still pass the test.
