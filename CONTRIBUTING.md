# Contributing

Tollgate holds its own changes to the rules it holds for a project. This page says how to set up, check, and propose a change.

## Set up

1. Install the check tools: `python3 -m pip install -r requirements-dev.txt`. Tollgate itself needs only the Python standard library.
2. Install the hooks: run `/tollgate:init` in Claude Code, in your copy of this repository. It installs pre-commit with Tollgate's checks, and adds your SSH key as an owner.

## Check a change

- Tests: `python3 -m pytest -q tests`.
- Style: `ruff check .`.
- Writing: `python3 setup/check_writing.py`. It reads the change against main: plain words, docs that move with the code, and the commit messages.
- Diagrams: `python3 docs/diagrams/build.py --check`. A diagram is a spec drawn as SVG, never a Mermaid block.
- Agents: `python3 -m setup.agents --check`. Each file in `agents/` is written from a role file in `roles/`; after you change a role, run `python3 -m setup.agents`.

CI runs the same checks on each proposed change.

## Write

The rules for docs, comments, and commit messages are in the Writing section of [lenses/review.md](lenses/review.md). The words are in [CONTEXT.md](CONTEXT.md): one word for each thing.

- A commit subject has the form `type(scope): subject`. The body says why. The author is you, and no line credits an AI.
- A change to behavior, a command, a setting, or the architecture updates the docs, diagrams, and comments that describe it, in the same change.

## Propose a change

1. Open the change on GitHub from a branch. Its title has the form `type(scope): subject`: the change is squashed into one commit on main, and the title becomes its subject. release-please reads it to set the next version.
2. Fill in the template: what changes and why, how you checked it, and what is not tested.
3. The owner reviews it. A change to `.tollgate/` or to the copied checks needs the owner's signed approval.

Report a security hole privately, as [SECURITY.md](SECURITY.md) says.
