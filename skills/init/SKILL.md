---
name: init
description: Set up Tollgate in one project - check your rights on GitHub, write the settings and the workflows, and protect the main branch and the tags. Use when the user runs /tollgate:init or asks to add Tollgate to a repository.
---

# Set up Tollgate in this project

You set up Tollgate in the git repository of the current folder. Each step ends with a check. Do not go to the next step until the check passes.

`TG` below is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -m <module>`, from the project folder.

Words: a **freeze** locks a ticket's tests before the build. The **harness** is every file that decides how tests run.

## 1. Find the repository and your rights

1. Read `git remote get-url origin` and turn it into `owner/name`.
2. Run `python3 -m setup.check_rights owner/name`. It prints one level.
3. Tell the user the level and what it means, in one sentence:
   - `admin`: Tollgate protects the main branch and the tags under `tg/`.
   - `write`: the tests and the review run, but an admin must protect the main branch and the tags. Tollgate turns `auto_merge` off.
   - `copy`: the organization allows only local actions. Tollgate's code is copied into the project, and in step 3 the version is `copy`.
   - `none`: stop. The user needs write access.

Done when the user has seen the level.

## 2. Write the settings

1. Read the project: its language, its test command, how it installs what the tests need, and any lint or type check.
2. Find a way for the test command to write a JUnit XML report. Most test tools have a flag for it, for example `pytest --junitxml=report.xml` or `go test` with `go-junit-report`.
3. Ask the user, in one message, only what you cannot find: the paths that need a review (tier 3), the paths that need a person (tier 4), and who may approve with a comment.
4. Write `.tollgate/settings.json`. Put the test command under `checks.tests` with its `report`. Set `require_plan` to `false`: plan tags are not built yet. With level `write`, set `auto_merge` to `false`.
5. Run `python3 -m action.settings .tollgate/settings.json`.

Done when that command prints the settings with no error. Show the user the file.

## 3. Write the workflows

1. Get the commit of Tollgate to use: `gh api repos/mohamed-rekiba/tollgate/commits/main --jq .sha`. Tell the user the commit.
2. Run `python3 -m setup.write_workflows --version <commit>`. With level `copy`, run it with `--version copy` instead: it also copies Tollgate's code into `.tollgate/runner/`. It writes `.github/workflows/tollgate.yml`, which never changes, and sets `"version"` in the settings. A later upgrade changes only that line.
3. On a new branch `tollgate-setup`, commit `.tollgate/settings.json` and `.github/workflows/tollgate.yml`, push it, and open a pull request.
4. Ask the user to merge it. The workflows run only from the main branch, so nothing after this step works before the merge.

Done when `git fetch origin && git show origin/main:.github/workflows/tollgate.yml` prints the file.

## 4. Protect the main branch and the tags

- With level `admin`, run `python3 -m setup.apply_rulesets owner/name`. Main then takes changes only through pull requests, and nobody can move or delete a tag under `tg/`.
- With level `write`, run `python3 -m setup.apply_rulesets owner/name --print` and give the output to the user to pass to an admin.

Done when the script prints `already in place` for both rulesets on a second run, or when the user has the commands.

## 5. Tell the user

In three lines or fewer: the level of rights, the version, and whether the main branch and the tags are protected.
