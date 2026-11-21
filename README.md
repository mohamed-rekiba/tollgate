# Tollgate

Tollgate is a plugin for Claude Code and a GitHub Action. It lets an AI build a change to your software, and it keeps that change out of the main branch until tests that the AI cannot change pass it.

## Why it exists

An AI that writes code makes four kinds of mistake. It invents a function, a file, or a fact. It pads its work. It stops before the work is done. It weakens a test to make the test pass.

Written instructions do not stop these mistakes, because the AI can ignore them. Tollgate does not ask the AI to behave. GitHub locks the tests before the AI builds, and GitHub runs them after.

## Status

Stages 1 to 4 are built. The lock is proven on GitHub, and the loop, the task, and scale are proven with fake roles. No ticket has run with a real model yet, so every default is provisional. [docs/status.md](docs/status.md) lists what is built, what is proven, and what is not.

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

Use Tollgate for a project where an AI writes most of each change and the change must be right. Do not use it yet for work that matters: no part of it has run on a real project.

## Where to read more

- [docs/plan.md](docs/plan.md): the design, in plain words first and in detail after.
- [CONTEXT.md](CONTEXT.md): the words this project uses, one word for each thing.
- [docs/experiments/](docs/experiments/): what was tried, and what happened.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
