---
name: retro
description: Look back at a finished Tollgate task - its numbers, and at most 3 lessons, each written as a ticket. Use when the user runs /tollgate:retro or asks what went wrong or how a task went.
---

# Run a retro

`TG` is the plugin root: two folders above this skill's base directory.

1. Run `PYTHONPATH="$TG" python3 -m driver.retro --project . --task <task id>`. It writes `.tollgate/lessons/<task id>.md` with the numbers and at most 3 candidates.
2. Show the user the numbers table.
3. For each candidate, read the log of its ticket in `.tollgate/logs/<ticket>.jsonl`. Then write one ticket in `.tollgate/tickets/lesson-<task id>-<n>/ticket.md` that turns the lesson into one of: a test, a check, a change to a lens, or a stricter rule. Use the ticket format, with `plan: lessons`.
4. A lesson may make a rule stricter. It may never make one looser, such as raising a limit, removing a check, or adding a path to a lower tier. If a lesson needs a looser rule, write it as a question for the user instead.

Done when the user has seen the numbers and each lesson ticket's path. Open at most 3.
