# Diagrams

Every diagram in this repo is SVG, drawn by code here, in a light and a dark file. The `diagram` skill (`skills/diagram/SKILL.md`) says how to draw one. `python3 docs/diagrams/build.py` draws them all; `--check` fails when one is out of date.

- `src/*.json`: one spec per diagram: a flow, a sequence, a state machine, a class or ER diagram, or a scene.
- `build.py`: draws them all, plus the diagrams drawn from the code (`workflow`), the banner (`hero.py`), and the icon sheet.
- The engine ships with the plugin, in `diagram/`: `flow.py` (flows and the colors), `sequence.py` (sequence diagrams), `state.py` (state machines), `model.py` (class and ER diagrams), `scene.py` (scenes), `icons.py` (the icons), `aws.py` (AWS icons from the official package). Any project with the plugin draws its own diagrams with `python3 -m diagram build <folder>`.

## Shapes

A flow uses the standard flowchart shapes. Each step takes the shape of what it is.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="shapes-dark.svg">
  <img alt="The flowchart shapes" src="shapes.svg">
</picture>

## Sequence and state machine

A sequence diagram shows one scenario between parts, in time order, down the page. This one is one ticket, from the driver to the store.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="one-ticket-sequence-dark.svg">
  <img alt="One ticket, from the driver to the store" src="one-ticket-sequence.svg">
</picture>

A state machine shows the states one thing is in, and the events that move it between them. This one is a task's lifecycle.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="task-lifecycle-dark.svg">
  <img alt="A task's lifecycle" src="task-lifecycle.svg">
</picture>

## Class and ER diagrams

A class diagram shows types and how they relate. This one is the plan and its tickets, and the signed records that lock them.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="plan-model-dark.svg">
  <img alt="The plan and its tickets, and the records that lock them" src="plan-model.svg">
</picture>

An ER diagram shows what is stored and the keys that link it. The store keeps signed files, not a database; this one draws its records as tables.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="store-records-dark.svg">
  <img alt="The signed records the store keeps, and the keys that link them" src="store-records.svg">
</picture>

## Icons

Tollgate's own icons, drawn for this project. Use them by name in a spec (`"icon": "lock"`) or in a scene (`badge`).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="icons-dark.svg">
  <img alt="Tollgate's icons" src="icons.svg">
</picture>

## AWS icons

AWS's icons are not in this repo. The first AWS diagram downloads the official package from AWS into a cache on your machine, once, and a diagram copies in only the icons it uses, unchanged. AWS allows its icons in architecture diagrams. See https://aws.amazon.com/architecture/icons/ for the package and its terms.
