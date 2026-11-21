---
name: status
description: Show what Tollgate has done and what is still to do in this project, in two short lists, with the details under them. Use when the user asks what Tollgate is doing, what is left, what it cost, or what waits for them.
---

# Show the status

`TG` is the plugin root: two folders above this skill's base directory.

1. From the project folder, run `PYTHONPATH="$TG" python3 -m driver.report --project .`. It prints two short lists, **Done** and **Still to do**, then a table of details.
2. For a line that says a pull request "waits to merge", check it with `gh pr view <number> --json state,mergedAt`. The logs cannot see a merge made by a person. If it merged, say "merged".
3. Show the two lists first, as they are. Show the table only if the user asks for details or cost.
4. For one task, run it with `--task <task id>`. The report it writes in `.tollgate/reports/<task id>.md` starts with the same two lists.

Do not start, stop, or change anything. This skill only reads.
