# Status

This file says what is built, what is tested, and what is not. It changes with each task.

## What is built

| Part | State |
| --- | --- |
| Setup: README, license, word list, plan, plugin shell, CI | Done. The plugin installs from the catalog. |
| Stage 0: experiments | E1 (without rulesets), E3, E4 (in part), and E5 ran. E2 and the ruleset part of E1 wait for the owner. See [experiments/](experiments/). |
| Stage 1: the lock (1.1 to 1.11) | Built and unit tested. An independent review found eight ways around the lock; all are fixed, each with a test. The composite action ran on a GitHub runner ([S1](experiments/S1-action-on-a-runner.md)). The freeze and gate workflows have not run on GitHub yet. |
| Stage 1: Tollgate guards its own repository (1.12) | Not done. Owner task 3 below. |
| Stage 2: the loop (2.1 to 2.8) | Built. The stage proof passes with fake roles against a local server, in CI. The container sandbox and the driver's GitHub client have not run. |
| Stage 2: one real ticket (2.9) | Not done. Owner task 5 below. |
| Stages 3 and 4 | Not built. They wait for task 2.9: its cost and time decide the defaults for a whole task. |

The `copy` level of rights (an organization that allows only local actions) is not built. `/tollgate:init` stops there and says so.

## Why the work stopped here

The session that built stages 1 and 2 could push branches and open and merge pull requests, but it could not start a workflow by hand, create a ruleset, push a tag, or run a container. Every step that is left needs one of those. Each owner task below says which.

## Owner tasks, in order

1. **Review the pull requests that guard the lock.** Read them first, in this order: #7 (eight fixes from an independent review), #4 (the freeze and gate workflows), #3 (the gate rules), #5 (rulesets and the gate proof).
2. **Run the stage 1 proof on a lab repository.** Create an empty repository where you are admin, then:

   ```
   PYTHONPATH=. python3 tests/proof_stage1.py <you>/<lab-repo> --ref <commit of main>
   ```

   Every line must end with `"holds": true`. It also answers E1's open question: whether the tag ruleset lets the freeze workflow create a tag and rejects one from your laptop.
3. **Guard this repository (1.12).** Run `/tollgate:init` here. Until then, nothing forces a merge to wait for the gate.
4. **Run E2 and E3.** E2: [scripts/e2_closed_room.sh](experiments/scripts/e2_closed_room.sh), on a machine with Docker or Podman. E3: [scripts/e3_fake_check.md](experiments/scripts/e3_fake_check.md). The gate posts its result as the check `tollgate gate`. If a workflow added in a pull request can post a check with that name and GitHub counts it, add the review workflow as a second required check for every tier.
5. **Run one real ticket (2.9).** On the lab repository from task 2, write one ticket, set `ai.builder` and `ai.reviewer` to `claude -p`, and run:

   ```
   PYTHONPATH=<tollgate> python3 -m driver.driver --project . --ticket <id>
   ```

   Write a note in `docs/experiments/` with the cost, the time, the attempts, and whether the pull request merged through the gate.
6. **Clean up the lab branches** listed in [experiments/lab-cleanup.md](experiments/lab-cleanup.md).
7. **Rename the plan document** in Claude from "Lockkeeper plan" to "Tollgate plan". The session could not change its title.

## Deviations from the plan

- From stage 2 on, the plan wants each task built from a ticket frozen by hand. The freeze needs a workflow started by hand on this repository, which the session could not do, so stage 2 was built with ordinary tests and pull requests.
- The workflow templates are named `tollgate-freeze.yml` and `tollgate-gate.yml`, the same as the files they become in a project. The review workflow (`tollgate-review.yml`) comes with stage 3.
- The gate posts its result as a check run named `tollgate gate`, so an approval comment (`tollgate approve <sha>`) or `tollgate check` can run it again on the latest commit.
- The `stronger` decision of an AI advisor runs one more attempt with the same builder: the settings have no key for a stronger model yet.
