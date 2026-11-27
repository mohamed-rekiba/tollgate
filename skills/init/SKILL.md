---
name: init
description: Set up Tollgate in a project on this machine. It writes the settings, and installs the checks that run before each commit, merge, and push. Use when the user runs /tollgate:init or asks to add Tollgate to a repository.
---

# Set up Tollgate in this project

You set up Tollgate in the git repository of the current folder. Each step ends with a check. Do not go to the next step until the check passes.

`TG` below is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -P -m <module>`, from the project folder.

Words: the **state folder** holds Tollgate's records outside the project, where no AI role can write. The **harness** is every file that decides how tests run. A **check** is one of the project's own commands, such as its tests or its lint. It lives as a hook in the project's `.pre-commit-config.yaml`, so the project works without Tollgate, and the settings name the hook.

## 1. Write the settings

1. Read the project: its language, its test command, how it installs what the tests need, and any lint or type check. Read its `.pre-commit-config.yaml` too, if it has one: a hook there may already run a check.
2. Find a way for the test command to write a JUnit XML report. Most test tools have a flag for it, for example `pytest --junitxml=report.xml` or `go test` with `go-junit-report`.
3. Ask the user, in one message, only what you cannot find: the paths that need a security review (tier 3) and the paths that need a person (tier 4).
4. Write the settings as a draft in a file outside the project, such as `$TMPDIR/tollgate-settings.json`. The guard does not let this session write `.tollgate/settings.json`; init writes it in step 2. For each check, name its hook when the config already has one: `"tests": {"hook": "check-tests", "report": "report.xml"}`. Otherwise put the command under `run`, such as `"vet": {"run": "go vet ./..."}`: init writes it once as a local hook `check-<name>` that runs before each push, and the settings then name that hook. The test check also has its `report`. Leave `require_plan` at its default, `true`: a ticket of tier 2 or more then needs a plan that the task locked, and `/tollgate:task` writes and locks one. Set `isolation` to `"container"`, the default, when Docker runs on this machine; otherwise set it to `"sandbox"`.

Done when the draft holds the checks and the tiers. Show the user the draft.

## 2. Run init

1. Confirm the current branch is `main`: `git branch --show-current`. If not, ask the user to switch to it.
2. Run `python3 -m setup.init --settings "$TMPDIR/tollgate-settings.json"`. It checks the draft and writes it as `.tollgate/settings.json`. It also checks that `claude`, `uv` and `pre-commit` are installed, and that Docker runs when `isolation` is `"container"`. It creates the state folder, and copies Tollgate's checks into `.tollgate/checks/`. In `.pre-commit-config.yaml` it adds or updates one hook, `tollgate`, writes the hooks of the checks that the draft keeps under `run`, and keeps every other repo and hook as it is. It commits these files on main, and runs `pre-commit install`.
3. If it stops because Docker is missing or not running, tell the user to start Docker, or to set `isolation` to `"sandbox"`. If it stops because a tool is missing, tell the user the install command: `brew install uv` for `uv` (or https://docs.astral.sh/uv/), `uv tool install pre-commit`, or `npm install -g @anthropic-ai/claude-code` for `claude`. Run it again after the install.
4. If `.tollgate/settings.json` already exists and differs from the draft, init stops and leaves it as it is. Ask the user to edit it, or to delete it, then run init again. If init stops because the config writes a list on one line, such as `repos: [...]`, ask the user to write it as a block list, one item on each line, then run init again.

Done when init ends with 0 and its last line says pre-commit is installed.

## 3. Check it

Run `python3 -m setup.health`. Done when it prints no warning. A warning about the plugin's Claude Code hooks means the plugin is out of date: tell the user to update it. A warning that a check names a hook that is not in `.pre-commit-config.yaml` means the gate cannot run that check: add the hook, or name another one in the settings, with the user's consent.

## 4. Tell the user

In three lines or fewer: the commit init made, that `spec` in the settings can name the design docs and the folder of decision records, and that `/tollgate:task` starts a task and `/tollgate:merge` merges a ready change.
