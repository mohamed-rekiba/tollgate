---
name: status
description: Show the state of Tollgate tasks and tickets in this project - state, tier, attempts, score, cost, pull request, and what waits for a decision. Use when the user asks what Tollgate is doing, what it cost, or what waits.
---

# Show the status

`TG` is the plugin root: two folders above this skill's base directory.

1. From the project folder, run `PYTHONPATH="$TG" python3 -m driver.report --project .`. It prints a table from the logs.
2. For one task, also run `PYTHONPATH="$TG" python3 -m driver.report --project . --task <task id>` and read the report it writes in `.tollgate/reports/<task id>.md`.
3. Show the table as it is. Under it, in one line each, name every ticket that waits for a person and the issue to answer, if the log names one.

Do not start, stop, or change anything. This skill only reads.
