---
name: status
description: Show what Tollgate has done and what is still to do in this project, in two short lists, with the details under them. It warns when a layer of the checks is missing. Use when the user asks what Tollgate is doing, what is left, what it cost, or what waits for them.
---

# Show the status

`TG` is the plugin root: two folders above this skill's base directory.

1. From the project folder, run `PYTHONPATH="$TG" python3 -m setup.health`. Show each warning first, as it is. A warning means a layer of the rules is off: the checks pre-commit runs before a commit, merge, or push, or the plugin's Claude Code hooks. Tell the user to run `/tollgate:init` to fix a missing pre-commit part, or to update the plugin for missing hooks.
2. Run `PYTHONPATH="$TG" python3 -m driver.report --project .`. It reads what ran on this machine and prints two short lists, **Done** and **Still to do**, then a table of details. Roadmaps show as one line each: their tasks done, the task now running, or why they stopped.
3. Show the two lists as they are. Show the table only if the user asks for details or cost.
4. For a change that waits to merge, say that `/tollgate:merge` merges it. For a question that waits for the user, say that `/tollgate:inbox` shows it.
5. For one task, add `--task <task id>`. The report it writes starts with the same two lists.

Do not start, stop, or change anything. This skill only reads.
