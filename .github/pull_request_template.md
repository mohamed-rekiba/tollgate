## What changes, and why

<!-- Lead with the change. One topic for each paragraph. -->

## How it was checked

<!-- The tests you added or ran, and their result. -->

## Not tested

<!-- Say plainly what is unfinished, untested, or unverified. Write "nothing" if so. -->

## Before you ask for a merge

- [ ] The title has the form `type(scope): subject`. It becomes the commit on main.
- [ ] The tests pass: `uv run --no-project --with-requirements requirements-dev.txt pytest -q -n auto tests`.
- [ ] `uv run --no-project --with-requirements requirements-dev.txt ruff check .` and `uv run --no-project python setup/check_writing.py` pass.
- [ ] The docs, diagrams, and comments that describe what changed are updated.
