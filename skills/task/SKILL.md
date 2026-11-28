---
name: task
description: Run a Tollgate task in this project, from a request or from a brief that /tollgate:brainstorm wrote. It analyzes the project, plans the task, has the plan reviewed, locks the tests, builds each ticket until its tests pass, and reviews the whole task. By default this session runs each role as a subagent, step by step, and the reviewers of one plan or change in parallel; the background driver is the other mode. A request too large for one plan becomes a roadmap of tasks. Use when the user runs /tollgate:task or asks Tollgate to build something.
---

# Run a task

The driver decides every step, the gate scores every try, and the store signs and merges. In session mode, the default, this session runs each role the driver asks for as one of Tollgate's subagents. In background mode the driver runs each role as its own process, and this session only starts it.

`TG` is the plugin root: two folders above this skill's base directory.

Words: a **task** is what the user asks for, in their own words. The **driver** analyzes the project, plans the task, cuts it into tickets, builds each ticket behind the gate, and reviews the whole task at the end. A **roadmap** is an ordered list of tasks, for a request too large for one plan. A **step** is one role the driver needs, with its prompt.

## 1. Check the project

1. Confirm that `.tollgate/settings.json` exists on the main branch: `git show main:.tollgate/settings.json`. If it does not, stop and tell the user to run `/tollgate:init` first.
2. Run `PYTHONPATH="$TG" python3 -P -m gate.settings .tollgate/settings.json`. Done when it prints the settings with no error.
3. Run `PYTHONPATH="$TG" python3 -P -m setup.health`. If it prints a warning, show it to the user and ask whether to go on: a missing layer means fewer checks hold.
4. Read `runner` in the settings that step 2 printed: `session` (the default) or `background`.

## 2. Get the request

1. Take the request from the user's message. If it is empty, ask for it in one question.
2. Pick a task id: a few lower-case words joined by `-`, such as `webhook-retries`. Use only `a` to `z`, `0` to `9`, and `-`, so the id is safe in a command and a file name. It must not match a file in `.tollgate/plans/` or `.tollgate/roadmaps/`. Tell the user the id.
3. Write the request, in the user's own words, to `.tollgate/requests/<task id>.md`.

Done when the file exists.

**From a brief.** When the user gives `--brief <brief id>`, the brief that `/tollgate:brainstorm` wrote is the request. Use the brief id as the task id, unless it matches a file in `.tollgate/plans/` or `.tollgate/roadmaps/`. Then run:

```
PYTHONPATH="$TG" python3 -P -m gate.brief --project . "<brief id>" --to ".tollgate/requests/<task id>.md"
```

It checks the brief, copies it as the request, and prints its `size`. If it ends with an error, show it to the user and stop. With size `task`, the brief's goals and non-goals set the scope of the plan, and the driver makes each question under `Open questions` an assumption of the plan. With size `roadmap`, step 3 makes a roadmap: use the brief's goals as the request.

## 3. One plan, or a roadmap

A brief of size `roadmap` always needs one. A request needs a roadmap when one plan cannot hold it: it builds a new service or app, or it names several features that depend on each other, such as "build an order service with login and an admin page". Anything smaller is one task. When in doubt, use one task.

For one task, go to step 4 in session mode, or step 5 in background mode.

For a roadmap:

1. Write `.tollgate/roadmaps/<task id>.md` in the format at the top of `$TG/gate/roadmap.py`: the request in the user's words; under **Base**, the tasks that make the project build, test, and run, and pass the base suite; under **Skeleton**, one task for each rule all code must follow, then the thinnest path through the riskiest feature; under **Features**, only the features that are clear now, one task each; under **Not yet specified**, everything else in a few words. Each task line is `- <task id>: <the request for that task, in plain words>`.
2. Write the checklist for the whole request as a ticket, `.tollgate/tickets/<task id>-done/ticket.md`, in the format at the top of `$TG/gate/tickets.py`. Each must-have item is something the user asked for, checked from the outside.
3. If `base` in the settings has an empty command, tell the user which of the five base checks has none. The roadmap stops after the base tasks until all five pass.
4. Run `PYTHONPATH="$TG" python3 -P -c 'import sys; from gate import roadmap as rm; rm.parse(open(sys.argv[1]).read())' ".tollgate/roadmaps/<task id>.md"`. Done when it ends with no error.
5. Run it in the mode that `runner` names: in session mode as in step 4, with `--roadmap "<task id>"` in place of `--task "<task id>"`; in background mode as in step 5.

## 4. Session mode: run each step here

Run this from the project folder, as one command:

```
PYTHONPATH="$TG" python3 -P -m driver.step next --project . --task "<task id>"
```

For a roadmap, run `next` with `--roadmap "<task id>"` in place of `--task "<task id>"`. It freezes the checklist's tests, runs each task of the roadmap in order, checks the base suite after the base tasks, and goes on to the next task when one is done. Its steps and its answers are the same as for one task.

It prints one JSON object. Loop on it:

- **A step**, `{"agent", "prompt", "cwd", "key", "nonce"}`: start the subagent named in `agent`, such as `tollgate:builder`. Its message is one line, `Your folder: <cwd>`, then a blank line, then the `prompt` exactly as printed. When it ends, write its whole final answer, unchanged, to a file outside the project, such as `$TMPDIR/tollgate-answer.md`, and run:

  ```
  PYTHONPATH="$TG" python3 -P -m driver.step answer --project . --key "<key>" --nonce "<nonce>" < "$TMPDIR/tollgate-answer.md"
  ```

  It saves the answer and prints the next object. Loop again. An object with `retry` is the same step again: the answer had no final json block, as when the subagent ran out of turns. Tell the user its reason in one line, and start the subagent again as for any step.
- **Steps that run at once**, `{"steps": [{"agent", "prompt", "cwd", "key", "nonce"}, ...]}`: reviewers that read the same plan or the same change and not one another. Start one subagent for each step, all in one message, so they run in parallel. Treat each one as a step above: when it ends, write its answer to its own file, such as `$TMPDIR/tollgate-answer-<key>.md`, and run `answer` with that step's own key and nonce. Run the `answer` commands one at a time, in any order. Each answer but the last prints `{"saved": <key>, "waiting": [keys]}`: the keys of the steps whose answers are still due. The last answer prints the next object. A `retry` object is for its step only: start that subagent again, and answer it with the same key and nonce.
- **A question**, `{"question": {"n", "title", "body", "options"}}`: show the user the title, the body, and the options, and ask which option they pick, with an optional hint. Record their answer the way `/tollgate:inbox` does: `PYTHONPATH="$TG" python3 -P -m setup.inbox --project . answer <n> <decision> [hint]`. Then run `next` again. Never pick an option for the user. If they have no answer yet, stop: `/tollgate:task` with the same task id goes on later.
- **The end**, `{"done": true, "result", "merged", "report"}`, or for a roadmap `{"done": true, "roadmap", "tasks", "result", "merged", "reports"}`: go to step 6.
- **Parked**, `{"parked": <reason>}`: tell the user the reason and stop. A roadmap whose base suite fails parks with the checks that failed; `next` with the same `--roadmap` goes on once they pass.
- **An error**, `{"error": <reason>}`: show it to the user and stop. If it says to run `/tollgate:init`, the task cannot pass until they do.

Never give the nonce to a subagent, and never put it in a file in the project. Never edit a file of the copy yourself, never change an answer, and never answer for a subagent: the driver asks again for anything it has no answer to. Run `next` again at any time to see the steps that wait. `next` prints a new nonce for each waiting step, so after it, answer only with the nonces it printed; it leaves out the steps already answered. The cost of the roles is your session's own; the report shows it as unknown.

## 5. Background mode: start the driver

Use this step only when `runner` is `background`. The driver runs on this machine, in the background. Its logs go to the state folder. Find the folder once:

```
logs="$(PYTHONPATH="$TG" python3 -P -c 'from gate import state; print(state.path(".", "logs"))')"
```

**A task:** run this from the project folder, as one command:

```
PYTHONPATH="$TG" python3 -P -c 'import subprocess, sys; out = open(sys.argv[1], "ab"); subprocess.Popen([sys.executable, "-P", "-m", "driver.task", "--project", ".", "--task", sys.argv[2], "--request-file", sys.argv[3]], stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)' "$logs/task-<task id>.out" "<task id>" ".tollgate/requests/<task id>.md"
```

**A roadmap:**

```
PYTHONPATH="$TG" python3 -P -c 'import subprocess, sys; out = open(sys.argv[1], "ab"); subprocess.Popen([sys.executable, "-P", "-m", "driver.roadmap", "--project", ".", "--roadmap", sys.argv[2]], stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)' "$logs/roadmap-<task id>.out" "<task id>"
```

`start_new_session=True` starts it as its own process, on Linux and on macOS, so closing this session does not stop it. Done when `$logs/task-<task id>.jsonl` or `$logs/roadmap-<task id>.jsonl` exists, within 60 seconds. If it does not, show the user the last 20 lines of the `.out` file and stop. A roadmap that stops can be started again the same way: it skips the tasks it finished, and the task it was in starts again.

## 6. Tell the user

In two lines: the task id, whether it is one task or a roadmap (and its tasks), and where it stands: in session mode the `result` that `next` printed and the tickets in `merged`; in background mode, that `/tollgate:status` shows progress. When the driver needs a person, `/tollgate:inbox` shows its question. When a change passes the gate, `/tollgate:merge` merges it.
