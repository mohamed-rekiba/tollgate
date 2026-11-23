---
name: diagram
description: Draw a diagram as an SVG file in light and dark, one that a person reads at a glance: a flowchart in the standard shapes, a UML sequence diagram, a UML state machine, a C4 diagram of software architecture, a UML use case diagram, a UML class diagram, an ER diagram, an isometric scene for the big picture, or an AWS architecture with the official AWS icons. Use whenever a README, doc, plan, or report needs a diagram, a flowchart, a sequence or state diagram, a C4 or architecture picture, a use case, class, or ER diagram, or icons. Never use Mermaid or a picture of text.
---

# Draw a diagram

`TG` is the plugin root: two folders above this skill's base directory. The diagrams of a project live in one folder, `docs/diagrams/` unless the project already has another. Each diagram is a JSON spec in `<folder>/src/<name>.json`; the command draws `<name>.svg` and `<name>-dark.svg` next to it:

```sh
PYTHONPATH="$TG" python3 -P -m diagram build docs/diagrams          # draw them all
PYTHONPATH="$TG" python3 -P -m diagram build docs/diagrams --check  # 1 if one is out of date
```

## Write for a person

The reader has never seen the project's code. Every word in the picture is for them.

- Use plain words. No ids, tag names, hashes, file paths, job names, or code names in a box. "Lock the tests", not "freeze-lock" or `tg/freeze/T-12/1`. A name from the code may appear once, small, on the last line of a box, when the reader needs it to find the code.
- Use the same word for the same thing in every diagram and in the text around it.
- Name the real thing. "Your laptop", not "the client"; "the gate", not "the checker".
- A box has a title of a few words, then at most two short lines.
- One diagram, one idea, about ten boxes at most. Split a bigger one.
- `desc` says what the picture means, in one or two sentences, for someone who cannot see it.

## Pick the kind

- A process, steps, choices: a **flow**. See below.
- One scenario between parts over time, such as a request between services or an API call: a **sequence**. See below.
- One thing with a lifecycle, the states it is in and the events that move it, such as an order or a task: a **state machine**. See below.
- The software architecture of a system, the C4 way: who uses it and what it talks to (context), the parts it runs as (container), the parts inside one of those (component), one scenario as numbered steps (dynamic), or where each part runs (deployment): a **C4 diagram**. See below.
- Who uses a system, and for what: a **use case diagram**. See below.
- Types and how they relate: what each holds, what inherits, owns, or uses what: a **class diagram**. See below.
- Stored data: tables or records, their keys, and how many of one go with another: an **ER diagram**. See below.
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
- `kind`: who acts or drives the step: `you` (blue), `ai` (purple), `server` (green), `check` (amber), `advisor` (orange). It sets the color, the icon, and the small label over the title. Use the same kind for the same actor everywhere. Name it for the reader: `"names": {"server": "Your machine"}` makes the label say YOUR MACHINE, because "the server" alone tells a reader nothing. Give every box the kind closest to its meaning: a diagram that is all gray reads as unfinished, and the test refuses it. Leave a box gray only when it is outside the story, like a legend.
- `icon`: another icon by name. The sheet of icons is `$TG/docs/diagrams/icons.svg`. `step` adds STEP n; `tag` sets the small label.
- `edges`: arrows. `label` says what travels or why. `tone` is `pass` (green) or `fail` (red), always with a label. `dashed` is a side path. `loop` (left, right, above, below) is an arrow that goes back. `route` (vhv, vh, hv) picks where it bends.
- `groups`: a border around boxes that belong together, such as "For each ticket".
- `ticket`: one dot that travels a path of arrows, to show one thing moving through. At most once per diagram.

## A sequence

A UML sequence diagram: one scenario between parts, in time order. Set `"type": "sequence"`. The format, with every option, is at the top of `$TG/diagram/sequence.py`. In short:

- `participants`: the parts, in a row across the top, each with a dashed lifeline down. `kind`, `icon`, `tag`, and `names` work as in a flow.
- `messages`: one row each, top to bottom. A call is a solid arrow. `"reply": true` is a reply: a dashed arrow with an open head. A message to the same participant is a self-message. `text` says what is asked or sent; `tone` is `pass` or `fail`.
- `activations`: a bar on a lifeline while that part is busy, from one message to another, counted from 0.
- `frames`: a box around messages. `loop` repeats them, `alt` picks one of two or more ways, `opt` happens only when its guard holds. Write each guard as a plain condition; the brackets are added.
- `"ticket": true`: one dot follows the messages in order.
- About ten to fourteen messages. Split a longer scenario.

## A state machine

A UML state machine: the states one thing is in, and the events that move it. Set `"type": "state"`. The format, with every option, is at the top of `$TG/diagram/state.py`. In short:

- `states`: boxes with round corners on a grid of `col` and `row`, with `kind` for who acts in that state. `"initial": true` is the start dot, `"final": true` the end ring.
- `parent`: puts a state inside another one, one level deep. The outer state may have its own start dot.
- `transitions`: arrows labeled with the `event`, then the `guard` in brackets, both optional. A transition from a state to itself is a loop, such as another try. `loop`, `route`, and `tone` work as in a flow; `shift` moves an arrow along a side so two arrows can share it.
- `ticket`: one dot follows a path of transitions, such as the path that works.
- About eight to twelve states. Name each for what is true while the thing waits there, such as "At the gate", not for a function.

## A C4 diagram

A diagram of software architecture, as C4 draws it, built on the flow. Set `"type": "c4"` and a `level`. The format, with every option, is at the top of `$TG/diagram/c4.py`. In short:

- `level`: `context`, `container`, `component`, `dynamic`, or `deployment`. It titles the picture, as in "Container diagram for Tollgate", and decides which elements it may hold: a wrong one is an error.
- `elements`: on a grid of `col` and `row`. Each has a `type`: `person` (a head over round shoulders), `system`, `container`, `database` (a cylinder), `queue` (a pipe), `component`, or `node` (a box in three dimensions). Give it a `name`, a `tech` for a container or a component, and a `description` of a few words. The type line comes from these, as in "[Container: Python]".
- `"external": true`: outside the thing the diagram is about. It is gray, and says so: "[External System]".
- `kind` and `names` work as in a flow. A person is `you` and the rest `server` by default.
- `boundaries`: a dashed box around the elements whose `parent` names it, as in "Tollgate [Software System]". One nests in another through its own `parent`. Keep the cells inside such a box for its own elements: the drawing refuses one that sits there without being inside.
- `relations`: arrows. `label` says what happens, `tech` says how; the drawing puts it under the label in brackets. Every relation needs a label.
- At the `dynamic` level the arrows are numbered 1, 2, 3 in the order you list them.
- At the `deployment` level each of the `boundaries` is a UML node: a box in three dimensions, with its `type` as a stereotype, as in "Your machine «device»". Nest a Docker or Python «execution environment» inside it. A `node` element with a `stereotype` is a node that holds nothing.
- Keep two lines in a box: a short description, wrapped. Put an arrow's label where the gap has room: an arrow that goes straight across or straight down gets room for its label.

## A use case diagram

A UML use case diagram, built on the flow. Set `"type": "usecase"`. The format, with every option, is at the top of `$TG/diagram/usecase.py`. In short:

- `system`: the name of the system. Its border holds every use case.
- `actors`: people or roles, drawn as a person, outside the border, on a grid of `col` and `row`.
- `cases`: ovals inside the border, each a goal in a few words, such as "Approve a change".
- `links`: a plain line from an actor to a use case. `"type": "include"` or `"extend"` joins two use cases with a dashed arrow labeled «include» or «extend». Put the two in one column or one row, so the label has room.

## A class diagram

A UML class diagram: the types of one part and how they relate. Set `"type": "class"`. The format, with every option, is at the top of `$TG/diagram/model.py`. In short:

- `classes`: boxes on a grid of `col` and `row`, in three compartments: the `name`, the `fields`, the `methods`. Leave out `fields` or `methods` and that compartment is not drawn. `stereotype` goes over the name in guillemets; `"abstract": true` sets the name in italics. `kind`, `icon`, and `names` work as in a flow.
- `relations`: read each as a sentence, `from` first. `type` is `inherits` or `implements` (a hollow triangle at `to`), `owns` (a filled diamond at `from`, the whole), `has` (a hollow diamond at `from`), `association` (a plain line; `"arrow": true` adds an open arrow), or `uses` (a dashed line with an open arrow). `composition`, `aggregation`, and `dependency` are the UML names for owns, has, and uses.
- `ends`: the multiplicity by each end, such as `["1", "0..*"]`; `roles` a role name before it. `label` sits in the middle. `route`, `loop`, and `shift` work as in a state machine.
- Field and method names are names the reader types, so write them as in the code. About eight classes; leave out the fields that do not matter to the point.

## An ER diagram

An entity relationship diagram: what is stored, and the keys that link it. Set `"type": "er"`. The format is at the top of `$TG/diagram/model.py`. In short:

- `tables`: boxes on a grid of `col` and `row`, with a `name` and `columns`: each a `name`, a `type`, and a `key` of `pk`, `fk`, or `pk fk`, drawn as small PK and FK tags.
- `relations`: a line with a crow's foot end at each table. `ends` names them, the end at `from` first: `exactly one`, `zero or one`, `one or many`, `zero or many` (`one` and `many` for short). `label`, `route`, `loop`, and `shift` work as in a class diagram.
- Table and column names are names the reader types, so write them as in the code or the database, such as `base_commit`.
- When the data is not in a database, such as signed files, draw the records and the keys that truly link them, and say so in `desc`.

## A scene

An isometric picture: zones on the ground, objects on them, lanes with moving dots between them, and labels. Set `"type": "scene"`. The format is at the top of `$TG/diagram/__init__.py`.

- Objects: `room` (a glass room with a worker inside), `gate` (a booth with a barrier), `server`, `database`, `vault` (a locked box), `papers`, `laptop`, `board` (a chart), `house`, `wall`, `pedestal` (a stand with any icon), `aws` (an AWS icon on a stand), `person` (someone who uses the system, in the color of its kind), `external` (a system that is not ours: a gray building, gray whatever its kind).
- A C4 system context as a scene: a `person` for each user, your system on its own zone in the middle, an `external` for each outside system, and a lane with a label for what flows between each pair.
- Ground units: x runs down-right on the page, y runs down-left. Put things that happen first on the left.
- Put each label beside its object, never over another object or label.
- A `ticket` travels the lanes; `lift` names the leg during which a gate opens.

## AWS architecture

- A node with `"aws": "s3"` (or `lambda`, `dynamodb`, `apigw`, `ecs`, or a name from AWS's package) shows the official AWS icon with its name under it.
- A group with `"aws": "vpc"` draws AWS's own border and corner icon. Groups: `cloud`, `account`, `region`, `az`, `vpc`, `public subnet`, `private subnet`, `security group`, `auto scaling`, `data center`. Nest them in AWS's order: Cloud, Region, VPC, Availability Zone, subnet.
- The first AWS diagram downloads the official package from AWS, once, into `~/.cache/tollgate/aws-icons` on this machine. Nothing goes into git. If there is no network, tell the person to download it from https://aws.amazon.com/architecture/icons/ and run `PYTHONPATH="$TG" python3 -P -m setup.aws_icons --zip <file>`.
- AWS allows its icons in architecture diagrams, unchanged. Never crop, recolor, rotate, or redraw one.

## Check it

1. Look at both files the way a reader will. Open them in a browser, or render them: `rsvg-convert -z 1.3 <file>.svg -o /tmp/x.png`, then read the PNG.
2. Fix anything that overlaps: a label on a box, an arrow through text, two labels touching. Move a node, pick another `route`, or shorten the words.
3. Keep it under about 1000 pixels wide, so the text stays readable on a code host's page.

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
- No scripts and no outside files, so a browser or a code host shows it as it is.
- Text dark or light enough to read in both themes: 4.5 to 1 for text, 3 to 1 for lines.
- Color means who acts, and the words say it too, so nobody needs the color.
- Motion only shows direction, and stops for a reader who turns on "reduce motion".
- A full square background, so no corner shows through on a page of the other theme.
