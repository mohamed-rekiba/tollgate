---
name: diagram
description: Draw a diagram as an SVG file in light and dark, one that a person reads at a glance - a flowchart in the standard shapes, an isometric scene for the big picture, or an AWS architecture with the official AWS icons. Use whenever a README, doc, plan, or report needs a diagram, a flowchart, an architecture picture, or icons. Never use Mermaid or a picture of text.
---

# Draw a diagram

`TG` is the plugin root: two folders above this skill's base directory. The diagrams of a project live in one folder, `docs/diagrams/` unless the project already has another. Each diagram is a JSON spec in `<folder>/src/<name>.json`; the command draws `<name>.svg` and `<name>-dark.svg` next to it:

```sh
PYTHONPATH="$TG" python3 -m diagram build docs/diagrams          # draw them all
PYTHONPATH="$TG" python3 -m diagram build docs/diagrams --check  # 1 if one is out of date
```

## Write for a person

The reader has never seen the project's code. Every word in the picture is for them.

- Use plain words. No ids, tag names, hashes, file paths, job names, or code names in a box. "Lock the tests", not "freeze-lock" or `tg/freeze/T-12/1`. A name from the code may appear once, small, on the last line of a box, when the reader needs it to find the code.
- Use the same word for the same thing in every diagram and in the text around it.
- A box has a title of a few words, then at most two short lines.
- One diagram, one idea, about ten boxes at most. Split a bigger one.
- `desc` says what the picture means, in one or two sentences, for someone who cannot see it.

## Pick the kind

- A process, steps, choices: a **flow**. See below.
- The big picture: places, who holds what, what talks to what: a **scene**. See below.
- Cloud infrastructure on AWS: a **flow** with AWS icons and AWS groups. See below.

## A flow

The format, with every option, is at the top of `$TG/diagram/flow.py`. In short:

- `nodes`: boxes on a grid of `col` and `row`. `text` is the title, then the lines under it, split by `\n`.
- `shape`: what the step is, in the standard flowchart shapes:
  - `start` and `end`: a pill. Where the flow begins and ends.
  - `step`: a box. Something is done. The default.
  - `decision`: a diamond. A yes or no question; give it two arrows out, each with a label.
  - `io`: a slanted box. Something comes in or goes out.
  - `document`: a page with a wavy foot. A plan, a report, a file a person reads.
  - `data`: a cylinder. Something stored: a database, locked tests.
  - `subprocess`: a box with double sides. A step that has its own diagram.
  - `wait`: a D. The flow waits, for a person or for time.
  - `manual`: a trapezoid. A person does it by hand.
- `kind`: who acts: `you`, `ai`, `server`, `check`, `advisor`. It sets the color, the icon, and the small label over the title. Use the same kind for the same actor everywhere. No kind is neutral gray.
- `icon`: another icon by name. The sheet of icons is `$TG/docs/diagrams/icons.svg`. `step` adds STEP n; `tag` sets the small label.
- `edges`: arrows. `label` says what travels or why. `tone` is `pass` (green) or `fail` (red), always with a label. `dashed` is a side path. `loop` (left, right, above, below) is an arrow that goes back. `route` (vhv, vh, hv) picks where it bends.
- `groups`: a border around boxes that belong together, such as "For each ticket".
- `ticket`: one dot that travels a path of arrows, to show one thing moving through. At most once per diagram.

## A scene

An isometric picture: zones on the ground, objects on them, lanes with moving dots between them, and labels. Set `"type": "scene"`. The format is at the top of `$TG/diagram/__init__.py`.

- Objects: `room` (a glass room with a worker inside), `gate` (a booth with a barrier), `server`, `database`, `vault` (a locked box), `papers`, `laptop`, `board` (a chart), `house`, `wall`, `pedestal` (a stand with any icon), `aws` (an AWS icon on a stand).
- Ground units: x runs down-right on the page, y runs down-left. Put things that happen first on the left.
- Put each label beside its object, never over another object or label.
- A `ticket` travels the lanes; `lift` names the leg during which a gate opens.

## AWS architecture

- A node with `"aws": "s3"` (or `lambda`, `dynamodb`, `apigw`, `ecs`, or a name from AWS's package) shows the official AWS icon with its name under it.
- A group with `"aws": "vpc"` draws AWS's own border and corner icon. Groups: `cloud`, `account`, `region`, `az`, `vpc`, `public subnet`, `private subnet`, `security group`, `auto scaling`, `data center`. Nest them in AWS's order: Cloud, Region, VPC, Availability Zone, subnet.
- The first AWS diagram downloads the official package from AWS, once, into a cache on this machine. Nothing goes into git. If there is no network, tell the person to download it from https://aws.amazon.com/architecture/icons/ and run `PYTHONPATH="$TG" python3 -m setup.aws_icons --zip <file>`.
- AWS allows its icons in architecture diagrams, unchanged. Never crop, recolor, rotate, or redraw one.

## Check it

1. Look at both files the way a reader will. Open them in a browser, or render them: `rsvg-convert -z 1.3 <file>.svg -o /tmp/x.png`, then read the PNG.
2. Fix anything that overlaps: a label on a box, an arrow through text, two labels touching. Move a node, pick another `route`, or shorten the words.
3. Keep it under about 1000 pixels wide, so the text stays readable on GitHub.

## Put it in the markdown

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/<name>-dark.svg">
  <img alt="<the title>" src="docs/diagrams/<name>.svg">
</picture>
```

Write the paths relative to the markdown file. Commit the spec and both SVG files together.

## What every drawing already does

The command takes care of these; do not undo them by hand.

- Real text, a `title` and a `desc` a screen reader reads, and `role="img"`.
- No scripts and no outside files, so GitHub shows it as it is.
- Text dark or light enough to read in both themes: 4.5 to 1 for text, 3 to 1 for lines.
- Color means who acts, and the words say it too, so nobody needs the color.
- Motion only shows direction, and stops for a reader who turns on "reduce motion".
- A full square background, so no corner shows through on a page of the other theme.
