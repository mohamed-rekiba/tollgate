---
name: diagram
description: Draw a diagram for this project as an SVG file, light and dark, readable by a screen reader. Use whenever a doc, README, plan, or report needs a diagram, a flowchart, or a picture of how parts connect. Never use Mermaid or an image of text.
---

# Draw a diagram

Every diagram in this project is an SVG file. A test fails on a Mermaid block in any markdown file.

## Steps

1. Write a spec in `docs/diagrams/src/<name>.json`. Use a short name in lowercase with dashes. The format is at the top of `docs/diagrams/build.py`.
   - `title`: what the diagram is, in a few words.
   - `desc`: what it shows, in one or two sentences. A screen reader reads this aloud, so write the meaning, not the shapes.
   - `nodes`: each box sits on a grid of `col` and `row`. Use `"shape": "decision"` for a yes or no question and `"shape": "note"` for a side actor, like the advisor.
   - `edges`: an arrow from one node to another. Add `"loop": "left"` (or above, below, right) for an arrow that goes back, so a loop reads as a loop. Add `"dashed": true` for a path that is not the main one.
2. Run `python3 docs/diagrams/build.py`. It writes `<name>.svg` and `<name>-dark.svg`.
3. Look at the result. Render it with `rsvg-convert -z 1.3 docs/diagrams/<name>.svg -o /tmp/<name>.png` and read the PNG. Fix any label that covers a box or a line. A loop that crosses a label gets a larger `reach`.
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
- Text in a box is plain words, the same words the docs use. The first line is the name; the next lines explain.
- The root has `role="img"`, a `viewBox`, and `aria-labelledby` naming a `<title>` and a `<desc>`. Screen readers need all four.
- Text is real `<text>`, never a path. Search and copy then work.
- No `<script>`, no `<foreignObject>`, no event attributes, no external file. GitHub strips them, and they are a risk.
- Text has a contrast of 4.5 to 1 or more on its fill, and lines 3 to 1 or more on the page, in both themes. The colors in `build.py` meet this. Do not change them without checking.
- Do not rely on color alone. A decision is a diamond and a side path is dashed, so the meaning shows without color.
- Do not put `prefers-color-scheme` inside the SVG. Browsers ignore it when the SVG is an image. Use the two files and the `picture` element.

## When the generator cannot draw it

For a picture the grid cannot hold, write the SVG by hand in `docs/diagrams/`, with a `-dark.svg` twin. It must still pass the test.
