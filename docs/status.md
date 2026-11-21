# Status

This file says what is built, what is proven, and what is not.

## What is built

| Part | State |
| --- | --- |
| Setup: README, license, word list, plan, plugin, CI | Done. The plugin installs from the catalog. |
| Stage 0: experiments | E1, E3, E4, and E5 ran. E2 ran without a model ([E2](experiments/E2-closed-room.md)). |
| Stage 1: the lock | Built and proven on GitHub ([S2](experiments/S2-gate-on-github.md)). An honest build passed. Five cheats failed on the right rules. |
| Stage 1: Tollgate guards its own repository (1.12) | Done. One workflow, `tollgate.yml`, with `"version": "self"`: main's own code locks the tests and runs them again. Since 2026-11-21 the gate runs only in the driver, on your machine. |
| Stage 2: the loop | Built. Proven with fake roles in CI, and with every role in a container ([E2](experiments/E2-closed-room.md)). |
| Stage 3: the task | Built. Proven with fake roles in CI. On GitHub, the plan workflow locked a plan, and the review posted a pass for tier 1 and a failure for tier 4 with no model key. |
| The `copy` level of rights | Built. `"version": "copy"` runs a copy of Tollgate's code from `.tollgate/runner/`, for organizations that allow only local actions. Tested locally, not yet in such an organization. |
| Stage 4: scale | Built: roadmap, base suite, home with submodules, rules sync, inbox, retro. Proven with fake roles in CI. |

Every default (3 tries, 30 minutes, 10 USD a ticket, 60 USD a task, a pass score of 70) is provisional, until the 3.10 numbers are final.

## What is not proven, and why

| Item | State |
| --- | --- |
| 2.9: one real ticket | Done. Built by the driver on GitHub with real models: one try, 0.93 USD, 4 minutes. See [T2.9](experiments/T2.9-first-real-ticket.md). |
| 3.10: Tollgate against Claude Code alone | Run, with two measures pending: the blind review, and the fixes after merge, due 2026-12-05. See [e310/results.md](experiments/e310/results.md). |
| E2: the closed room | Done, both halves. See [E2](experiments/E2-closed-room.md). |
| E3: a fake gate check | The risk is real. Whether a required check accepts the fake needs the rulesets on. See [E3](experiments/E3-fake-check.md). |
| An AI review on GitHub | Done. It passed #28 and #44 with the OAuth token. |
| The `copy` level of rights | Tested locally. Not yet run in an organization that allows only local actions. |

## The rulesets

The gate no longer runs on GitHub: the owner removed it on 2026-11-21. No ruleset requires a check.

To turn them on again, run `PYTHONPATH=. python3 -m setup.apply_rulesets tollgate-ai/tollgate`. With them on:

- **tollgate main**: changes come through pull requests, and main cannot be force-pushed or deleted.
- **tollgate tags**: nobody can move or delete a tag under `tg/`.

No normal change needs the admin bypass then: see "Nothing can deadlock" in [decisions.md](decisions.md).

## Questions for you

These need a person. The session leaves them open on purpose.

- Approve or close any pull request that waits on the label `tg-waiting` or on `tollgate approve <sha>`. Only you can give that approval.
