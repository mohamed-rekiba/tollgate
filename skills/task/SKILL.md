---
name: task
description: Start a Tollgate task in this project. It plans the task, has the plan reviewed, locks the tests, and builds each ticket until its tests pass. It runs in the background. A request too large for one plan becomes a roadmap of tasks. Use when the user runs /tollgate:task or asks Tollgate to build something.
---

# Start a task

You start the driver for one task and return. The driver keeps running after this session ends.

`TG` is the plugin root: two folders above this skill's base directory.

Words: a **task** is what the user asks for, in their own words. The **driver** plans it, cuts it into tickets, and builds each ticket behind the gate. A **roadmap** is an ordered list of tasks, for a request too large for one plan.

## 1. Check the project

1. Confirm that `.tollgate/settings.json` exists on the main branch: `git fetch origin && git show origin/main:.tollgate/settings.json`. If it does not, stop and tell the user to run `/tollgate:init` first.
2. Run `PYTHONPATH="$TG" python3 -m gate.settings .tollgate/settings.json`. Done when it prints the settings with no error.

## 2. Get the request

1. Take the request from the user's message. If it is empty, ask for it in one question.
2. Pick a task id: a few lower-case words joined by `-`, such as `webhook-retries`. Use only `a` to `z`, `0` to `9`, and `-`, so the id is safe in a command and a file name. It must not match a file in `.tollgate/plans/` or `.tollgate/roadmaps/`. Tell the user the id.
3. Write the request, in the user's own words, to `.tollgate/requests/<task id>.md`.

Done when the file exists.

## 3. One plan, or a roadmap

A request needs a roadmap when one plan cannot hold it: it builds a new service or app, or it names several features that depend on each other, such as "build an order service with login and an admin page". Anything smaller is one task. When in doubt, use one task.

For one task, go to step 4.

For a roadmap:

1. Write `.tollgate/roadmaps/<task id>.md` in the format at the top of `$TG/gate/roadmap.py`: the request in the user's words; under **Base**, the tasks that make the project build, test, and run, and pass the base suite; under **Skeleton**, one task for each rule all code must follow, then the thinnest path through the riskiest feature; under **Features**, only the features that are clear now, one task each; under **Not yet specified**, everything else in a few words. Each task line is `- <task id>: <the request for that task, in plain words>`.
2. Write the checklist for the whole request as a ticket, `.tollgate/tickets/<task id>-done/ticket.md`, in the format at the top of `$TG/gate/tickets.py`. Each must-have item is something the user asked for, checked from the outside.
3. If `base` in the settings has an empty command, tell the user which of the five base checks has none. The roadmap stops after the base tasks until all five pass.
4. Run `PYTHONPATH="$TG" python3 -c 'import sys; from gate import roadmap as rm; rm.parse(open(sys.argv[1]).read())' ".tollgate/roadmaps/<task id>.md"`. Done when it ends with no error.
5. Start it, on GitHub or here, as in step 4.

## 4. Start it: on GitHub, or on this machine

Run it on GitHub when the user asks for that, and for a roadmap, which can run for hours. GitHub needs the model access: `gh secret list` must show `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`. If neither is there, run it on this machine and tell the user that adding one of the two secrets lets the next one run on GitHub. Anything else runs on this machine.

**A task on GitHub:**

```
gh workflow run tollgate.yml --ref main -f kind=task -f id="<task id>" -f request="$(cat ".tollgate/requests/<task id>.md")"
```

**A roadmap on GitHub.** The run reads the roadmap and its checklist from the branch `tg-roadmap/<task id>`. Push them there without touching the user's working folder. The branch only carries these two files, so a new push replaces it:

```
git fetch -q origin main && tmp="$(mktemp -d)" && git worktree add -q --detach "$tmp" origin/main \
  && mkdir -p "$tmp/.tollgate/roadmaps" "$tmp/.tollgate/tickets" \
  && cp ".tollgate/roadmaps/<task id>.md" "$tmp/.tollgate/roadmaps/" \
  && cp -r ".tollgate/tickets/<task id>-done" "$tmp/.tollgate/tickets/" \
  && git -C "$tmp" add .tollgate && git -C "$tmp" commit -q -m "roadmap <task id>" \
  && git -C "$tmp" push -q --force origin "HEAD:refs/heads/tg-roadmap/<task id>"; git worktree remove --force "$tmp"
gh workflow run tollgate.yml --ref main -f kind=roadmap -f id="<task id>"
```

Done, for either, when `gh run list --workflow tollgate.yml --limit 3` shows `tollgate task <task id>` or `tollgate roadmap <task id>` within 60 seconds. If it does not, show the user the error and stop. A roadmap that runs out of GitHub's time can be started again the same way: it skips the tasks it finished, and the task it was in starts again.

**A task on this machine.** Run this from the project folder, as one command:

```
mkdir -p .tollgate/logs && setsid -f env PYTHONPATH="$TG" python3 -m driver.task --project . --task "<task id>" --request-file ".tollgate/requests/<task id>.md" > ".tollgate/logs/task-<task id>.out" 2>&1 < /dev/null
```

**A roadmap on this machine:**

```
mkdir -p .tollgate/logs && setsid -f env PYTHONPATH="$TG" python3 -m driver.roadmap --project . --roadmap "<task id>" > ".tollgate/logs/roadmap-<task id>.out" 2>&1 < /dev/null
```

`setsid -f` starts it as its own process, so closing this session does not stop it. Done when `.tollgate/logs/task-<task id>.jsonl` or `.tollgate/logs/roadmap-<task id>.jsonl` exists, within 60 seconds. If it does not, show the user the last 20 lines of the `.out` file and stop.

## 5. Tell the user

In two lines: the task id, whether it is one task or a roadmap (and its tasks), where it runs, and that `/tollgate:status` shows progress. Questions for a person appear as GitHub issues with the label `tg-waiting`. A person answers with a comment whose first line is `tollgate decide <decision>`.
