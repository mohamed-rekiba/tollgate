---
name: init
description: Set up Tollgate in one project - check your rights on GitHub, write the settings and the workflows, lock the gate, and prove that the gate rejects a changed test. Use when the user runs /tollgate:init or asks to add Tollgate to a repository.
---

# Set up Tollgate in this project

You set up Tollgate in the git repository of the current folder. Each step ends with a check. Do not go to the next step until the check passes.

`TG` below is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -m <module>`, from the project folder.

Words: the **gate** is the required check `tollgate gate`. A **freeze** locks a ticket's tests before the build. The **harness** is every file that decides how tests run.

## 1. Find the repository and your rights

1. Read `git remote get-url origin` and turn it into `owner/name`.
2. Run `python3 -m setup.check_rights owner/name`. It prints one level.
3. Tell the user the level and what it means, in one sentence:
   - `admin`: full protection. The gate becomes required.
   - `write`: the gate runs and shows pass or fail, but nothing forces a merge to wait. Tollgate turns `auto_merge` off.
   - `copy`: the organization allows only local actions. Stop here and say that this level is not built yet.
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

1. Get the commit of Tollgate to pin: `gh api repos/mohamed-rekiba/tollgate/commits/main --jq .sha`. Tell the user the commit.
2. Run `python3 -m setup.write_workflows --ref <commit>`.
3. On a new branch `tollgate-setup`, commit `.tollgate/settings.json` and `.github/workflows/tollgate-*.yml`, push it, and open a pull request.
4. Ask the user to merge it. The workflows run only from the main branch, so nothing after this step works before the merge.

Done when `git fetch origin && git show origin/main:.github/workflows/tollgate-gate.yml` prints the file.

## 4. Lock the gate

- With level `admin`, run `python3 -m setup.apply_rulesets owner/name`. It makes the gate required on the main branch and stops anyone from moving or deleting a tag under `tg/`.
- With level `write`, run `python3 -m setup.apply_rulesets owner/name --print` and give the output to the user to pass to an admin. Say plainly that until an admin runs it, the gate does not block a merge.

Done when the script prints `already in place` for both rulesets on a second run, or when the user has the commands.

## 5. Prove the gate

1. Pick the ticket id `proof-<today as yyyymmdd>`.
2. On the branch `tg/<ticket id>`, write `.tollgate/tickets/<ticket id>/ticket.md` with this header and sections, and write a test file in the project's own test tool:

   ```
   ---
   id: <ticket id>
   plan: proof
   seams: none
   tests: <path of the test file>
   ---
   ## Current behavior
   The function tollgate_proof does not exist.

   ## Desired behavior
   tollgate_proof returns "ok".

   ## Checklist
   - [C1, must] tollgate_proof returns "ok".
   - [C2, must] tollgate_proof takes no arguments.
   - [C3] tollgate_proof is documented.

   ## Out of scope
   Everything else.
   ```

   Name the tests so each one holds its item id, such as `test_c1_returns_ok` and `test_c2_takes_no_arguments`. Each must fail now, because the function does not exist.
3. Run the test command from the settings and confirm that both tests fail and appear in the report.
4. Commit and push the branch. Do not open a pull request.
5. Run `python3 -m setup.prove_gate owner/name --ticket <ticket id>`. It freezes the ticket, changes a locked test, opens a pull request, and waits for the gate. It can take up to 15 minutes.

Done when it prints `"proof": "passed"`. If it prints `"failed"`, show the user the reason and the summary, and stop.

## 6. Tell the user

In three lines or fewer: the level of rights, the pinned commit, and the result of the proof. With level `write`, repeat that the gate does not block a merge until an admin runs the ruleset commands.
