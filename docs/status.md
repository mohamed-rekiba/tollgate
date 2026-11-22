# Status

This file says what is built, what is verified, and what is not.

## What is built

| Part | Code | Verified by |
| --- | --- | --- |
| The state folder and the keys | `gate/state.py`, `gate/sign.py` | Unit tests |
| The store: locks, plan locks, pass records, ready changes, questions, merge | `gate/store.py` | Unit tests, with a real git repository and real `ssh-keygen` signatures |
| The gate and its six checks | `gate/gate.py`, `gate/tiers.py`, `gate/review.py` | Unit tests: each check has a passing and a failing case |
| The settings | `gate/settings.py` | Unit tests |
| The driver: one ticket, from the tests to a ready change | `driver/driver.py` | Unit tests, with fake roles |
| The task: plan, plan review, approval, plan lock, then each ticket | `driver/task.py` | Unit tests, with fake roles |
| The stop rules and the advisor | `driver/stop.py`, `driver/advisor.py` | Unit tests |
| Running a role, and the isolation | `driver/roles.py` | Unit tests of the command line it builds. No real run. |
| The roadmap and the base suite | `driver/roadmap.py`, `setup/base_suite.py` | No passing test |
| The retro | `driver/retro.py` | No passing test |
| The Claude Code hook and the policies | `hooks/guard.py`, `hooks/policy.py`, `hooks/hooks.json` | Unit tests of the hook's answers and of the rules it writes. No run inside Claude Code. |
| Setup and the pre-commit checks | `setup/init.py`, `setup/precommit.py`, `setup/check_*.py`, `setup/health.py` | Unit tests, and a test that runs pre-commit on the config it writes |
| Merge, inbox, home, and rules sync | `setup/merge.py`, `setup/inbox.py`, `setup/home.py`, `setup/sync_rules.py` | Unit tests |
| The skills | `skills/` | Read by hand. No skill runs in a test. |

`python3 -m pytest -q` runs the unit tests. The files `tests/proof_stage2.py`, `tests/proof_stage3.py`, and `tests/proof_stage4.py` do not match the local design and fail. Pytest does not collect them.

Every default (3 tries, 30 minutes, 10 USD a ticket, 60 USD a task, a pass score of 70, 4 plan rounds) is a first guess. No measure has set it.

## Experiments

| Experiment | Result |
| --- | --- |
| [L1](experiments/L1-role-obeys-its-settings.md): a role obeys its policy | Not run. `claude -p` has no model access on the build machine. |
| [L2](experiments/L2-sandbox-blocks-python.md): the sandbox stops a write through Python | Not run, for the same reason. So the default isolation is `container`. |
| [L3](experiments/L3-pre-commit-stages.md): when pre-commit runs | Passed. A fast-forward merge skips every check, so the store merges with a merge commit. |

## What is not verified

- **The sandbox.** `"isolation": "sandbox"` is untested with Claude Code.
- **The container.** No role has run in Docker through the local driver. Tollgate ships no container image: you name one under `container_image`.
- **A real task.** No task has run end to end with real models through the local driver. The cost numbers in the README come from a run on hosted machines.
- **The lock run.** `Store.freeze` runs the tests in a temporary clone on your machine, not in the role's isolation.
- **A replaced lock.** The store allows a second lock for a ticket. The driver has no step that asks for one.
- **A split.** The advisor can choose split, but the driver parks the ticket and does not cut it.
- **Free paths.** The settings hold `free`, but no code reads it. A change made by hand needs your approval, at tier 4.
- **The comparison.** Two measures of [the comparison](experiments/e310/results.md) are open: the blind review, and the fixes after merge.

## Known gaps in other files

- `skills/init/SKILL.md` tells the user to set `require_plan` to `false` because plan locks are not built. The store builds plan locks.
- `skills/retro/SKILL.md` names `.tollgate/logs/` and `.tollgate/lessons/` in the project. The logs and lessons live in the state folder.
- The docstrings of `gate/manifest.py` and `gate/__init__.py` describe a GitHub tag and a GitHub Action, which Tollgate does not use.
