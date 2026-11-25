---
name: init
description: Set up Tollgate in a project on this machine. It writes the settings, and installs the checks that run before each commit, merge, and push. Use when the user runs /tollgate:init or asks to add Tollgate to a repository.
---

# Set up Tollgate in this project

You set up Tollgate in the git repository of the current folder. Each step ends with a check. Do not go to the next step until the check passes.

`TG` below is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -P -m <module>`, from the project folder.

Words: the **state folder** holds Tollgate's records outside the project, where no AI role can write. The **harness** is every file that decides how tests run.

## 1. Write the settings

1. Read the project: its language, its test command, how it installs what the tests need, and any lint or type check.
2. Find a way for the test command to write a JUnit XML report. Most test tools have a flag for it, for example `pytest --junitxml=report.xml` or `go test` with `go-junit-report`.
3. Ask the user, in one message, only what you cannot find: the paths that need a security review (tier 3) and the paths that need a person (tier 4).
4. Write the settings as a draft in a file outside the project, such as `$TMPDIR/tollgate-settings.json`. The guard does not let this session write `.tollgate/settings.json`; init writes it in step 2. Put the test command under `checks.tests` with its `report`. Leave `require_plan` at its default, `true`: a ticket of tier 2 or more then needs a plan that the task locked, and `/tollgate:task` writes and locks one. Set `isolation` to `"container"`, the default, when Docker runs on this machine; otherwise set it to `"sandbox"`.

Done when the draft holds the checks and the tiers. Show the user the draft.

## 2. Run init

1. Confirm the current branch is `main`: `git branch --show-current`. If not, ask the user to switch to it.
2. Run `python3 -m setup.init --settings "$TMPDIR/tollgate-settings.json"`. It checks the draft and writes it as `.tollgate/settings.json`. It also checks that `claude`, `uv` and `pre-commit` are installed, and that Docker runs when `isolation` is `"container"`. It creates the state folder, copies the checks into `.tollgate/checks/`, writes `.pre-commit-config.yaml`, commits these files on main, and runs `pre-commit install`.
3. If it stops because Docker is missing or not running, tell the user to start Docker, or to set `isolation` to `"sandbox"`. If it stops because a tool is missing, tell the user the install command: `brew install uv` for `uv` (or https://docs.astral.sh/uv/), `uv tool install pre-commit`, or `npm install -g @anthropic-ai/claude-code` for `claude`. Run it again after the install.
4. If `.tollgate/settings.json` already exists and differs from the draft, init stops and leaves it as it is. Ask the user to edit it, or to delete it, then run init again. If the project already has a `.pre-commit-config.yaml` that Tollgate did not write, init stops. Move each of its hooks into `checks` in the draft, with the user's consent, then run init with `--replace`.

Done when init ends with 0 and its last line says pre-commit is installed.

## 3. Check it

Run `python3 -m setup.health`. Done when it prints no warning. A warning about the plugin's Claude Code hooks means the plugin is out of date: tell the user to update it.

## 4. Tell the user

In three lines or fewer: the commit init made, that `spec` in the settings can name the design docs and the folder of decision records, and that `/tollgate:task` starts a task and `/tollgate:merge` merges a ready change.
