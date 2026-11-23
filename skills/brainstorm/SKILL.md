---
name: brainstorm
description: Turn a rough idea into a brief before any plan. The builder asks one question at a time, the advisor answers, the idea is stated and confirmed, the analyst reads the project, and four fresh reviewers challenge the idea. The result is a brief in .tollgate/briefs that /tollgate:task --brief takes as its request. Use when the user runs /tollgate:brainstorm, or has an idea that is not yet clear enough to build.
---

# Brainstorm an idea

The driver decides every step, and the advisor answers every question: a person through the inbox, or an AI advisor, as `ai.advisor` in the settings says. In session mode, the default, this session runs each role the driver asks for as one of Tollgate's subagents. In background mode the driver runs each role as its own process.

`TG` is the plugin root: two folders above this skill's base directory.

Words: the **idea** is what the user wants, in their own words, before it is clear. A **brainstorm** turns it into a **brief**: an overview, what the reviewers found, the goals, the non-goals, the alternatives weighed, and the questions it could not settle. `/tollgate:task --brief` takes the brief as the request of a task.

## 1. Check the project

1. Confirm that `.tollgate/settings.json` exists on the main branch: `git show main:.tollgate/settings.json`. If it does not, stop and tell the user to run `/tollgate:init` first.
2. Run `PYTHONPATH="$TG" python3 -P -m gate.settings .tollgate/settings.json`. Done when it prints the settings with no error.
3. Read `runner` in the settings that step 2 printed: `session` (the default) or `background`.

## 2. Get the idea

1. Take the idea from the user's message. If it is empty, ask for it in one question.
2. Pick an id: a few lower-case words joined by `-`, such as `csv-export`. Use only `a` to `z`, `0` to `9`, and `-`. It must not match a file in `.tollgate/briefs/` or `.tollgate/ideas/`. Tell the user the id.
3. Write the idea, in the user's own words, to `.tollgate/ideas/<id>.md`.

Done when the file exists.

## 3. Session mode: run each step here

Run this from the project folder, as one command:

```
PYTHONPATH="$TG" python3 -P -m driver.step next --project . --brainstorm "<id>"
```

It prints one JSON object. Loop on it as `/tollgate:task` does in its step 4:

- **A step**, `{"agent", "prompt", "cwd", "key", "nonce"}`: start the subagent named in `agent`. Its message is one line, `Your folder: <cwd>`, then a blank line, then the `prompt` exactly as printed. When it ends, write its whole final answer, unchanged, to a file outside the project, such as `$TMPDIR/tollgate-answer.md`, and run:

  ```
  PYTHONPATH="$TG" python3 -P -m driver.step answer --project . --key "<key>" --nonce "<nonce>" < "$TMPDIR/tollgate-answer.md"
  ```

  It saves the answer and prints the next object. Loop again.
- **A question**, `{"question": {"n", "title", "body", "options"}}`: show the user the body and the options. For a question about the idea, the options are `answer`, with their answer as the hint, and `skip`, when they do not know. For the statement of the idea, they are `confirm`, and `add`, with what the statement misses as the hint. Record their words the way `/tollgate:inbox` does: `PYTHONPATH="$TG" python3 -P -m setup.inbox --project . answer <n> <decision> [hint]`. Then run `next` again. Never answer for the user. If they have no answer yet, stop: `/tollgate:brainstorm` with the same id goes on later.
- **The end**, `{"done": true, "brief", "size", "open_questions"}`: go to step 5.
- **Parked**, `{"parked": <reason>}`: tell the user the reason and stop.
- **An error**, `{"error": <reason>}`: show it to the user and stop.

Never give the nonce to a subagent, never edit the brief, and never change an answer.

## 4. Background mode: start the driver

Run this from the project folder, as one command:

```
PYTHONPATH="$TG" python3 -P -c 'import subprocess, sys; from gate import state; out = open(state.path(".", "logs", f"brainstorm-{sys.argv[1]}.out"), "ab"); subprocess.Popen([sys.executable, "-P", "-m", "driver.brainstorm", "--project", ".", "--brainstorm", sys.argv[1]], stdout=out, stderr=out, stdin=subprocess.DEVNULL, start_new_session=True)' "<id>"
```

When the advisor is a person, each question waits in `/tollgate:inbox`. Run the same command again after the user answers: the brainstorm repeats no finished step. Done when `.tollgate/briefs/<id>.md` exists.

## 5. Tell the user

In three lines: the path of the brief, its size, and the number of questions under `Open questions`. Then the next step:

- Size `task`: `/tollgate:task --brief <id>`. Each question under `Open questions` becomes an assumption of the plan, so the advisor answers them before the plan is locked.
- Size `roadmap`: the idea is too big for one task. `/tollgate:task --brief <id>` writes a roadmap from it.
