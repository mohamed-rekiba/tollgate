# Tollgate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/hero-dark.svg">
  <img alt="Tollgate: let AI write your code, merge only what works" src="docs/diagrams/hero.svg">
</picture>

Tollgate lets an AI build changes to your software, and keeps each change out of your main branch until it passes tests the AI cannot change.

It is a plugin for Claude Code, plus one GitHub workflow. You ask for a change in plain words. Tollgate plans it, cuts it into small tickets, has the tests written and locked first, has the code built, checks it, and opens a pull request. The gate, a program with no AI in it, decides whether a change is ready for a pull request. On GitHub, the tests run again and an AI reviews the riskier changes.

The website: https://tollgate-ai.github.io/ (its source is in [tollgate-ai.github.io](https://github.com/tollgate-ai/tollgate-ai.github.io)).

## What you gain

- **The AI cannot grade its own work.** A check with no AI decides every merge, and no AI can override it.
- **The AI cannot weaken a test to pass it.** Tests are written from the ticket and locked on GitHub before any code exists. They must fail first, and nobody can change them after.
- **"Done" means the same thing every time.** A ticket passes only when each must-have item is proven by a locked test, or by a file and line that Tollgate confirms exists.
- **Less invented code reaches you.** Separate AI sessions write the tests, build, and review. Each reviewer starts fresh and cannot edit. It looks for one thing: behavior nobody asked for, untested logic, or ways to misuse the change.
- **You step in only when it matters.** Small changes go through on their own. Changes to risky paths, such as security code, the test setup, or the workflows, wait for you to merge them.
- **Work does not stall or loop.** Tollgate retries from its best attempt with what went wrong, and stops after 3 tries, the same failure twice, 30 minutes, or a cost limit. Then the advisor, a second AI or you, decides what happens next.
- **You can leave it running.** One request becomes a plan and a pull request for each ticket. A stopped run picks up where it was.
- **The AI cannot reach your accounts.** The builder works in a container on a copy of your project, with model access only: no git or GitHub credentials.
- **You see where things stand at a glance.** `/tollgate:status` gives two short lists, Done and Still to do.
- **It improves with use.** `/tollgate:retro` shows a task's numbers and turns at most 3 lessons into tickets. A lesson can make a rule stricter, never looser.
- **Little to install, nothing to run.** One workflow file that never changes, one settings file, Python's standard library, and no server.

## The principles

1. **Tests come first.** Before the AI writes any code, Tollgate writes tests for what you asked for and locks them. The AI cannot change them.
2. **The AI never grades its own work.** The tests and fresh reviewers check it.
3. **Every try gets a score.** 70% or more passes. A failed must-have item always fails.
4. **Each try builds on the best one.** When a try fails, the AI gets the reasons and tries again from its best try so far.
5. **It knows when to stop.** After 3 tries, the AI asks for help: a second AI, or you.
6. **Riskier changes get more checks.** You merge the riskiest ones yourself.
7. **Mistakes become rules.** After each task, up to 3 lessons become stricter rules. Rules never get looser.
8. **Code enforces the rules.** A rule that is only written in a prompt does not count.
9. **Plain words.** Everything is written for people to read.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/principles-dark.svg">
  <img alt="Tollgate's principles: tests come first, others check each try, 70% passes, a failed try goes again from the best one, after 3 tries the AI asks for help, and lessons become rules for the next task" src="docs/diagrams/principles.svg">
</picture>

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/how-it-works-dark.svg">
  <img alt="How Tollgate works, with its three feedback loops" src="docs/diagrams/how-it-works.svg">
</picture>

Three loops keep the work honest:

1. **The build loop.** When the gate or a reviewer finds a problem, the findings and each failed check's output go back to the builder. It tries again from its best attempt, until it passes or a stop rule sends the ticket to the advisor.
2. **The plan loop.** Reviewers read the plan before any code exists. The builder fixes, contests, or escalates each finding, for up to 4 rounds.
3. **The learning loop.** After a task, `/tollgate:retro` turns at most 3 lessons into tickets: a new test, a new check, a new question for the reviewers, or a stricter rule. The next tasks run under them.

Each change gets a tier from 1 to 4 from the paths it touches. With `auto_merge` on, Tollgate merges a tier 1 or 2 change itself. A tier 3 or 4 change waits for you to merge it, after an AI reviews it on GitHub.

Code enforces every rule above. A rule that is only written in a prompt does not count. [docs/plan.md](docs/plan.md) explains each part.

## Get started

You need Claude Code, Python 3.11 or later, git, and the `gh` command.

```
/plugin marketplace add tollgate-ai/tollgate
/plugin install tollgate@tollgate-ai
```

Then, inside your project:

```
/tollgate:init
```

`init` checks your rights on GitHub. It writes `.tollgate/settings.json` and `.github/workflows/tollgate.yml`. Then it protects the main branch and the tags.

To run tasks on GitHub instead of your machine, add one of these repository secrets: `CLAUDE_CODE_OAUTH_TOKEN` (get it with `claude setup-token`), or `ANTHROPIC_API_KEY`.

## Use it

| You type | What happens |
| --- | --- |
| `/tollgate:task` | Starts a task from your request. It runs in the background. |
| `/tollgate:status` | Shows Done and Still to do. |
| `/tollgate:inbox` | Lists what waits for your decision, across projects. |
| `/tollgate:retro` | Shows a finished task's numbers and lessons. |
| `/tollgate:home` | Keeps the plans of many projects in one private repository. |
| `/tollgate:docs` | Writes a README, docs, comments, commit messages, and pull requests in plain words. It adds a check for the writing rules. |
| `/tollgate:diagram` | Draws a diagram as an SVG file, in light and dark. |

A question for you arrives as a GitHub issue with the label `tg-waiting`. You answer with a comment that starts `tollgate decide`, followed by your choice.

## Cost, and when to use it

On ten small tickets, Tollgate cost about 10 times as much as Claude Code alone, and took 2 to 4 times as long: about 0.7 USD and 3 minutes a ticket. In return, every change it opened passed its checks. We do not know yet whether it also needs fewer fixes after the merge. That is still being measured. See [the comparison](docs/experiments/e310/results.md).

Use Tollgate when an AI writes most of each change, and the change must be right. For a quick change where a mistake is cheap, use Claude Code alone. It is faster and cheaper.

## Status

Built and working:

- the gate, and the step that locks the tests,
- the driver, the program that runs each step, on your machine or on GitHub,
- the plan, review, and advisor steps,
- many projects in one home.

Still being measured: the blind review and the fixes after merge from [the comparison](docs/experiments/e310/results.md). [docs/status.md](docs/status.md) has the details.

## Read more

- [docs/plan.md](docs/plan.md): the design, in plain words first and in detail after.
- [docs/decisions.md](docs/decisions.md): each decision, and why.
- [CONTEXT.md](CONTEXT.md): the words this project uses, one for each thing.
- [docs/experiments/](docs/experiments/): what was tried, and what happened.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
