---
name: task
description: Start a Tollgate task in this project - plan it, review the plan, lock it, and build each ticket behind the gate, in the background. Use when the user runs /tollgate:task or asks Tollgate to build something.
---

# Start a task

You start the driver for one task and return. The driver keeps running after this session ends.

`TG` is the plugin root: two folders above this skill's base directory.

Words: a **task** is what the user asks for, in their own words. The **driver** plans it, cuts it into tickets, and builds each ticket behind the gate.

## 1. Check the project

1. Confirm that `.tollgate/settings.json` exists on the main branch: `git fetch origin && git show origin/main:.tollgate/settings.json`. If it does not, stop and tell the user to run `/tollgate:init` first.
2. Run `PYTHONPATH="$TG" python3 -m action.settings .tollgate/settings.json`. Done when it prints the settings with no error.

## 2. Get the request

1. Take the request from the user's message. If it is empty, ask for it in one question.
2. Pick a task id: a few lower-case words joined by `-`, such as `webhook-retries`. It must not match a file in `.tollgate/plans/`. Tell the user the id.
3. Write the request, in the user's own words, to `.tollgate/requests/<task id>.md`.

Done when the file exists.

## 3. Start the driver

Run this from the project folder, as one command:

```
mkdir -p .tollgate/logs && setsid -f env PYTHONPATH="$TG" python3 -m driver.task --project . --task <task id> --request-file .tollgate/requests/<task id>.md > .tollgate/logs/task-<task id>.out 2>&1 < /dev/null
```

`setsid -f` starts it as its own process, so closing this session does not stop it.

Done when `.tollgate/logs/task-<task id>.jsonl` exists, within 30 seconds. If it does not, show the user the last 20 lines of `.tollgate/logs/task-<task id>.out` and stop.

## 4. Tell the user

In two lines: the task id, and that `/tollgate:status` shows progress. Questions for a person appear as GitHub issues with the label `tg-waiting`. A person answers with a comment whose first line is `tollgate decide <decision>`.
