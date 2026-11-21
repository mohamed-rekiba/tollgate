# Diagrams

Every diagram in this repo is SVG, drawn by code here, in a light and a dark file. The `diagram` skill (`skills/diagram/SKILL.md`) says how to draw one. `python3 docs/diagrams/build.py` draws them all; `--check` fails when one is out of date.

- `src/*.json`: the flat blueprint diagrams, one spec each.
- `scenes.py`: the isometric scenes, drawn with the kit in `iso.py`.
- `build.py`: diagrams drawn from the code, such as `workflow`, and the list of scenes and art.
- `hero.py`: the README banner.
- `driver/diagram.py`: the flat engine and the colors. `driver/icons.py`: the icons. `driver/aws.py`: AWS icons from the official package.

## Icons

Tollgate's own icons, drawn for this project. Use them by name in a spec (`"icon": "lock"`) or in a scene (`badge`).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="icons-dark.svg">
  <img alt="Tollgate's icons" src="icons.svg">
</picture>

## AWS icons

AWS's icons are not in this repo. `python3 -m setup.aws_icons` fetches the official package from AWS into a cache on your machine, and a diagram copies in only the icons it uses, unchanged. AWS allows its icons in architecture diagrams. See https://aws.amazon.com/architecture/icons/ for the package and its terms.
