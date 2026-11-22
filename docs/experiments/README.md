# Experiments

Each file here records one experiment: the question, what was run, and the result. The status page, [../status.md](../status.md), says what each result means for Tollgate.

## Experiments for the local design

| File | Question | Result |
| --- | --- | --- |
| [L1](L1-role-obeys-its-settings.md) | Does a role obey the permission rules and the hook in its own Claude Code settings? | Not run: `claude -p` has no model access on the build machine. |
| [L2](L2-sandbox-blocks-python.md) | Does Claude Code's sandbox stop a write through `python -c`? | Not run, for the same reason. |
| [L3](L3-pre-commit-stages.md) | On which git steps does pre-commit run? | Passed. A fast-forward merge skips every check. |

Each file of L1 and L2 says how to run it. Run them on a machine where `claude -p` has model access.

## Other records

These files record experiments on parts that Tollgate does not use: GitHub rulesets, workflows, and hosted machines. They hold the data of each run as it happened.

- [E1](E1-locks.md), [E3](E3-clean-server-job.md), [E3, the fake check](E3-fake-check.md), [E5](E5-pinned-action.md), [S1](S1-action-on-a-runner.md), [S2](S2-gate-on-github.md), and [the lab cleanup](lab-cleanup.md).
- [E2](E2-closed-room.md): a role in a container sees only its copy and the model access. This bears on `"isolation": "container"`, but it ran with a different driver.
- [E4](E4-long-run.md): a driver that keeps running after the Claude Code session closes.
- [T2.9](T2.9-first-real-ticket.md) and [the comparison with Claude Code alone](e310/results.md): the only runs with real models. Their costs and times are in the README.
