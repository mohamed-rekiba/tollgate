---
id: roadmap-check-cli
plan: e310b-03
seams: action.roadmap.main, python3 -m action.roadmap
tests: tests/test_roadmap_cli.py
---
## Current behavior
action/roadmap.py has parse() and RoadmapError but no command line.

## Desired behavior
`python3 -m action.roadmap <path>` checks one roadmap file. For a good file it prints each task in build order (Base, Skeleton, Features) with its stage, and exits 0. For a bad file it prints the error and exits 1.

## Checklist
- [C1, must] A valid roadmap prints one line per task, in build order, each line holding the stage, the task id, and the task request; main returns 0.
- [C2, must] A roadmap that parse rejects prints the RoadmapError message (prefixed `error: `) and main returns 1; nothing is printed as a task.
- [C3, must] A path that does not exist, or cannot be read, prints an `error:` line and returns 1, with no traceback.
- [C4] Running `python3 -m action.roadmap <path>` as a subprocess gives the same output and exit code as main.
- [C5, must, keeps behavior] parse() and its errors are unchanged.

## Out of scope
Checking that the checklist ticket exists; reading roadmaps by id; other commands.
