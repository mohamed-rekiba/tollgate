# Tollgate

Tollgate is a plugin for Claude Code and a GitHub Action. It lets an AI build a change to your software, and it keeps that change out of the main branch until tests that the AI cannot change pass it.

## Why it exists

An AI that writes code makes four kinds of mistake. It invents a function, a file, or a fact. It pads its work. It stops before the work is done. It weakens a test to make the test pass.

Written instructions do not stop these mistakes, because the AI can ignore them. Tollgate does not ask the AI to behave. GitHub locks the tests before the AI builds, and GitHub runs them after.

## Principles

Each principle names the part of Tollgate that enforces it. A rule that only a prompt states is not counted.

1. **A gate decides, not an AI.** A check with no AI decides whether a change may merge, and no AI can override it. *Enforced by* `action/gate.py`, on GitHub.
2. **Tests come before code.** A test writer writes tests from the ticket, and GitHub locks them before the build. They must fail before it, and nobody can change them after. *Enforced by* the freeze tag and the run that recorded it.
3. **Roles are kept apart.** The test writer, builder, reviewer, and advisor are separate sessions with their own tools. The reviewer starts with no history and cannot edit. *Enforced by* `roles/` and the tool list for each role.
4. **A script runs the steps.** The driver runs them in a fixed order, keeps its state in a log, and starts again without repeating a finished step. *Enforced by* `driver/driver.py` and `driver/task.py`.
5. **Each attempt climbs toward a score.** The score is the share of checklist items proven to pass. Each attempt starts from the best so far and from what failed, until the score reaches 70. *Enforced by* `score()` in the driver.
6. **Attempts stop, then someone decides.** After 3 attempts, the same failure twice, 30 minutes, or a cost limit, the advisor decides: retry, a stronger builder, split, or park. The advisor is an AI or a person. *Enforced by* the stop rules and `driver/advisor.py`.
7. **Risk sets the checks.** The paths a change touches give it a tier from 1 to 4. A higher tier adds a review on the server and an approval by a person. *Enforced by* `action/tiers.py`.
8. **The builder works in a closed room.** The builder runs in a container on a copy of the project. It gets only model access, with no git or GitHub credentials. *Enforced by* the container command and the workflow permissions.
9. **Claims need evidence.** A checklist item passes only by a locked test, or by a file and a line that the driver confirms exists. *Enforced by* `score()`.
10. **Measure, then improve.** `/tollgate:retro` gives the numbers and at most 3 lessons, each as a ticket. A lesson may make a rule stricter, never looser. The experiment in [docs/experiments/e310](docs/experiments/e310/results.md) compares Tollgate with Claude Code alone.
11. **Keep it light.** One workflow file that never changes, the version as data in the settings, and nothing that can deadlock. Plain files, Python's standard library, and no service to run.

## Status

Stages 1 to 4 are built. The lock and the gate are proven on GitHub. The driver has built real tickets with real models on GitHub Actions. The comparison with Claude Code alone has run, with two measures still pending. [docs/status.md](docs/status.md) lists what is built, what is proven, and what is not.

## How to start

You need Claude Code, Python 3.11 or later, and git.

```
/plugin marketplace add mohamed-rekiba/tollgate
/plugin install tollgate@mohamed-rekiba
```

Then, inside a project:

```
/tollgate:init
```

## When to use it

Use Tollgate for a project where an AI writes most of each change and the change must be right. It costs more than Claude Code alone: about 10 times the model use and 2 to 4 times the time on small tickets. Whether that buys fewer fixes after merge is still being measured.

## Where to read more

- [docs/plan.md](docs/plan.md): the design, in plain words first and in detail after.
- [CONTEXT.md](CONTEXT.md): the words this project uses, one word for each thing.
- [docs/experiments/](docs/experiments/): what was tried, and what happened.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
