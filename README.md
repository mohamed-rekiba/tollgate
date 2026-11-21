# Tollgate

Tollgate is a plugin for Claude Code and a GitHub Action. It lets an AI build a change to your software, and it keeps that change out of the main branch until tests that the AI cannot change pass it.

## Why it exists

An AI that writes code makes four kinds of mistake. It invents a function, a file, or a fact. It pads its work. It stops before the work is done. It weakens a test to make the test pass.

Written instructions do not stop these mistakes, because the AI can ignore them. Tollgate does not ask the AI to behave. GitHub locks the tests before the AI builds, and GitHub runs them after.

## What you gain

Each benefit comes from one principle, and code enforces each principle. A rule that only a prompt states is not counted.

1. **The AI cannot grade its own work.** A check with no AI decides whether a change may merge, and no AI can override it. *How:* the gate, `action/gate.py`, runs on GitHub.
2. **The AI cannot weaken a test to pass it.** Tests are written from the ticket and locked before any code exists. They must fail first, and nobody can change them after. *How:* GitHub stores a freeze of the tests, and the gate checks it.
3. **"Done" means the same thing every time.** A ticket passes only when every must-have item is proven by a locked test, or by a file and line that Tollgate confirms exists. Claims without evidence count as failures. *How:* the score in the driver.
4. **Fewer invented names and less padding reach you.** The builder, the test writer, and the reviewers are separate sessions. Each reviewer starts fresh, cannot edit, and looks for one thing: behavior nobody asked for, untested logic, ways to misuse the change. *How:* the role and lens files.
5. **You step in only when it matters.** Small, low-risk changes go through on their own. Changes to risky paths, such as security code, the test setup, or the workflows, wait for your approval. *How:* each change gets a tier from 1 to 4, from the paths it touches.
6. **Work does not stall or loop for ever.** Tollgate retries from its best attempt, with what failed, and stops after 3 tries, the same failure twice, 30 minutes, or a cost limit. An advisor then decides: retry, a stronger model, split the ticket, or park it. The advisor is an AI or you. *How:* the driver's stop rules.
7. **You can leave it running.** One request becomes a plan, then small tickets, each built and checked in turn, with a pull request for each. A run that is stopped picks up where it was. *How:* the driver keeps its state in a log.
8. **The AI cannot reach your accounts.** The builder works in a container on a copy of your project, with model access only: no git or GitHub credentials. *How:* the container and the workflow permissions.
9. **You see where things stand at a glance.** `/tollgate:status` gives two short lists, Done and Still to do. `/tollgate:inbox` lists what waits for you across all your projects. *How:* the logs and the report.
10. **It gets better from use.** `/tollgate:retro` shows the numbers of a task and turns at most 3 lessons into tickets. A lesson may make a rule stricter, never looser. *How:* `driver/retro.py`.
11. **Little to install, nothing to run.** One workflow file that never changes, settings in one file, and an upgrade that is one line in a pull request. Plain files, Python's standard library, and no server. *How:* `"version"` in `.tollgate/settings.json`.

What it costs: on small tickets, about 10 times the model use of Claude Code alone, and 2 to 4 times the time. Whether that buys fewer fixes after merge is still being measured. See [the comparison](docs/experiments/e310/results.md).

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

Use Tollgate for a project where an AI writes most of each change and the change must be right. For a quick change where a mistake is cheap, Claude Code alone is faster and cheaper.

## Where to read more

- [docs/plan.md](docs/plan.md): the design, in plain words first and in detail after.
- [CONTEXT.md](CONTEXT.md): the words this project uses, one word for each thing.
- [docs/experiments/](docs/experiments/): what was tried, and what happened.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
