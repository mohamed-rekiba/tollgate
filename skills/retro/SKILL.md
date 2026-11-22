---
name: retro
description: Look back at a finished Tollgate task: its numbers, and at most 3 lessons, each written as a ticket. Use when the user runs /tollgate:retro or asks what went wrong or how a task went.
---

# Run a retro

`TG` is the plugin root: two folders above this skill's base directory. The logs and the lessons are in the project's state folder, outside the project. Find the folder once, from the project folder:

```
dir="$(PYTHONPATH="$TG" python3 -P -c 'from gate import state; print(state.state_dir("."))')"
```

1. Run `PYTHONPATH="$TG" python3 -P -m driver.retro --project . --task <task id>`. It writes `$dir/lessons/<task id>.md` with the numbers and at most 3 lessons, and prints its path.
2. Show the user the numbers table.
3. For each lesson, read the log of its ticket in `$dir/logs/<ticket>.jsonl`. Then write one ticket in `.tollgate/tickets/lesson-<task id>-<n>/ticket.md` that turns the lesson into one of: a test, a check, a change to a lens, or a stricter rule. Use the ticket format, with `plan: lessons`.
4. A lesson may make a rule stricter. It may never make one looser, such as raising a limit, removing a check, or adding a path to a lower tier. If a lesson needs a looser rule, write it as a question for the user instead.

Done when the user has seen the numbers and each lesson ticket's path. Open at most 3.
