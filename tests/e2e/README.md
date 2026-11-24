# End-to-end run with real subagents

This folder holds a script, `make_project.py`, that makes a throwaway project for one whole Tollgate task run by real Claude Code subagents: the analyst, the builder, the test writer, and the reviewers, each started by your own session, in session mode.

## Why it exists

The unit tests run every step of a task with a fake role, `tests/fake_role.py`. They prove that the driver, the store, and the gate do their part, but not that a real model can follow each role's prompt and give an answer the driver accepts. This run checks that, on a small project, with its own state folder and key folder, so it touches nothing of yours.

## It needs a model, so CI does not run it

The run starts real subagents, so it needs Claude Code, a signed-in account, and a model, and it costs tokens. No test and no CI run starts it. `tests/test_e2e_project.py` checks only the script: that it makes the project, and that `driver.step next` names a first step. That test runs no model.

## How to start

From this clone of Tollgate, with git, pre-commit, pytest, and claude installed:

```
python3 tests/e2e/make_project.py /tmp/tollgate-e2e
```

Give a folder that does not exist yet, or an empty one. It makes:

- `project/`: a git repository on main with `calc.py`, its tests, and Tollgate set up by `setup.init`, with a tests check that runs pytest. The request of the task is in `project/.tollgate/requests/e2e-divide.md`.
- `state/` and `keys/`: the state folder root and the key folder, for `TOLLGATE_STATE` and `TOLLGATE_KEYS`. The machine secret is made in `keys/` on first use.
- `gitconfig`: a git identity for the run, for `GIT_CONFIG_GLOBAL`.

Then it prints the exact commands for the run. In short:

1. In a new shell, export the variables it prints, go to `project/`, and start `claude --plugin-dir "$TG"`, so the session loads this clone as its plugin.
2. In that session, type `/tollgate:task` with the request, or run the loop of the task skill (`skills/task/SKILL.md`, step 4) by hand:
   - `PYTHONPATH="$TG" python3 -P -m driver.step next --project . --task e2e-divide` prints a step: `agent`, `prompt`, `cwd`, `key`, and `nonce`.
   - The main session plays the role: it starts the subagent named in `agent`, such as `tollgate:analyst`, with the line `Your folder: <cwd>`, a blank line, and the prompt exactly as printed. It writes the subagent's whole final answer, unchanged, to a file outside the project.
   - `driver.step answer --project . --key "<key>" --nonce "<nonce>" < <that file>` saves the answer and prints the next step.
   - A question for you, at the plan and at the end of the task, waits for your pick: answer it with `python3 -P -m setup.inbox --project . answer <n> <option>`, then run `next` again.
3. The run ends with `done`, `parked`, or an error. The report is in the state folder. Delete the whole folder when you are done.

## When to use it

Run it by hand before a release, and after a change to a role's prompt, to the subagents in `agents/`, to the step file, or to `driver/step.py`. For any other change, the unit tests are enough.
