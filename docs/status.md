# Status

This file says what is built, what is proven, and what is not.

## What is built

| Part | State |
| --- | --- |
| Setup: README, license, word list, plan, plugin, CI | Done. The plugin installs from the catalog. |
| Stage 0: experiments | E1, E3, E4, and E5 ran. E2 ran without a model ([E2](experiments/E2-closed-room.md)). |
| Stage 1: the lock | Built and proven on GitHub ([S2](experiments/S2-gate-on-github.md)). An honest build passed. Five cheats failed on the right rules. |
| Stage 1: Tollgate guards its own repository (1.12) | Settings and the four workflows are on main. The rulesets are the last step; see below. |
| Stage 2: the loop | Built. Proven with fake roles in CI, and with every role in a container ([E2](experiments/E2-closed-room.md)). |
| Stage 3: the task | Built. Proven with fake roles in CI. On GitHub, the plan workflow locked a plan, and the review posted a pass for tier 1 and a failure for tier 4 with no model key. |
| Stage 4: scale | Built: roadmap, base suite, home with submodules, rules sync, inbox, retro. Proven with fake roles in CI. |

Every default (3 attempts, 30 minutes, 10 USD a ticket, 60 USD a task, a pass score of 70) is provisional. No ticket has run with a real model yet.

## What is not proven, and why

| Item | Why not | What proves it |
| --- | --- | --- |
| A ticket built by a real model (2.9), and the experiment on 10 to 15 real tickets (3.10) | This session has no model key, and must not use its own model access as Tollgate's builder. | Set `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`), then run `/tollgate:task` on a lab project. `/tollgate:retro` gives the numbers. |
| The model half of E2: Claude Code inside the container | The same: no model key. | [scripts/e2_closed_room.sh](experiments/scripts/e2_closed_room.sh) |
| A model review on the server, for tier 3 and 4 | Not yet passed on GitHub. | Add the secret `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`, then comment `tollgate check` on a tier 3 pull request. |
| A forged freeze tag pushed from a laptop, and a tag push rejected by the ruleset | This session cannot create tags, and a forged tag through the REST API was refused as undermining oversight. | Unit tests cover the gate's side (`tests/test_review_findings.py`). With the rulesets on, `git tag tg/freeze/x/1 && git push origin tg/freeze/x/1` must be rejected. |
| E3: a fake check named `tollgate gate` from a workflow added in a pull request | It needs a workflow pushed on a branch, which is the attack itself. | [scripts/e3_fake_check.md](experiments/scripts/e3_fake_check.md) |
| The `copy` level of rights | Not built. It is for organizations that allow only local actions. | |

## The rulesets

`setup/apply_rulesets.py` creates two rulesets:

- **tollgate main**: the check `tollgate gate` is required on main, changes come through pull requests, and main cannot be force-pushed or deleted. A repository admin can bypass it, and GitHub logs it. No normal change needs the bypass: see "Nothing can deadlock" in [decisions.md](decisions.md).
- **tollgate tags**: nobody can move or delete a tag under `tg/` (pattern `refs/tags/tg/**/*`). In an organization, only GitHub Actions can create one. On a personal account, such as this repository's, GitHub does not accept an app as a bypass actor, so anyone with write access can create a `tg/` tag. The gate still rejects a freeze or plan tag that its run did not record.

Once they are on, a change needs a ticket with locked tests, or touches only free paths such as docs. Tier 4 also needs an approval by a person.

To roll them back: Settings, Rules, Rulesets, then turn off or delete `tollgate main` and `tollgate tags`. Or, with the GitHub CLI:

```
gh api repos/mohamed-rekiba/tollgate/rulesets --jq '.[] | "\(.id) \(.name)"'
gh api -X DELETE repos/mohamed-rekiba/tollgate/rulesets/<id>
```

## Questions for you

These need a person. The session leaves them open on purpose.

- Approve or close any pull request that waits on the label `tg-waiting` or on `tollgate approve <sha>`. Only you can give that approval.
- Delete the lab branches and tags in [experiments/lab-cleanup.md](experiments/lab-cleanup.md).
