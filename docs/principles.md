# Tollgate's principles

Tollgate lets an AI write your code, and merges only what works. Nine principles make that true. This page explains each one: what it means, why it exists, how Tollgate does it, and where it stops.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/principles-dark.svg">
  <img alt="Tollgate's principles: tests come first, others check each try, 70% passes, a failed try goes again from the best one, after 3 tries the AI asks the advisor, and lessons become rules for the next task" src="diagrams/principles.svg">
</picture>

Two words first. A **try** is one builder session, then one run of the gate. The **gate** is a program with no AI in it. It runs on your machine after each try and decides whether the try may become a pull request.

## 1. Tests come first

**What it means.** Before the AI writes any code, Tollgate writes the tests for what you asked for and locks them. The AI cannot change them.

**Why.** An AI that cannot make a test pass sometimes weakens the test. When the tests are fixed before the build, "done" cannot move.

**How Tollgate does it.**

- Each ticket has a checklist that says what "done" means. Each line is an item. A must-have item cannot fail.
- A separate AI, the test writer, writes one test for each must-have item. It writes the test at a seam: a public point where a test can observe behavior, such as a web address, a command, or a function's name and inputs.
- A reviewer confirms that each test fits its item, can fail, and does not take its expected result from the code it tests.
- GitHub runs the tests before any code exists. None may pass yet. GitHub then records each test file with its fingerprint and locks the record with a tag. This is the freeze.
- After the freeze, the gate fails any try that changes a locked file.

**Where it stops.** A locked test can be wrong. The builder cannot change it, but it can say so with evidence. The test writer then writes a new test, GitHub locks it as a second freeze, and you merge that change yourself. A ticket gets one replacement.

## 2. The AI never grades its own work

**What it means.** The tests and fresh reviewers check each try. The AI that built it does not.

**Why.** A review by the same AI that wrote the code defends the code.

**How Tollgate does it.**

- The locked tests check every must-have item.
- A reviewer checks each other item. Each reviewer is a separate AI session. It starts with no history and cannot edit anything. It must name the file and the line that prove an item, and the driver confirms that the line exists.
- Each reviewer looks for one thing, set by a lens: a file that tells it what to look for. One lens looks for behavior nobody asked for, one for new logic with no test, and one for ways to misuse the change.
- The gate itself uses no AI, so it gives the same answer every time.

## 3. Every try gets a score

**What it means.** The score is the share of checklist items that passed. A try needs 70% or more.

**Why.** "Done" should mean the same thing every time, and a number is hard to argue with.

**How Tollgate does it.**

- An item with a test passes when its test passes. A reviewer decides each other item.
- A try goes on only with a score of 70 or more. The setting is `pass_score`, and its default is 70.
- Every must-have item has a locked test, and the gate fails a try when a locked test fails. So no score can make up for a failed must-have item.

## 4. Each try builds on the best one

**What it means.** When a try fails, the AI gets the reasons and tries again, starting from its best try so far.

**Why.** Each try should get closer. Starting over loses what worked. Starting from the last try can build on a step backward.

**How Tollgate does it.**

- The driver keeps the commit of the try with the highest score.
- The next try starts from that commit.
- The builder gets the findings of the failed try and the output of each failed check.

## 5. It knows when to stop

**What it means.** The AI does not try forever. When it is stuck, it asks the advisor: a second AI, or you.

**Why.** A loop with no end burns money and time, and it hides a problem that needs a decision.

**How Tollgate does it.** The driver stops a ticket when one of these is true. Each limit is a setting under `stop`.

| Limit | Default |
| --- | --- |
| Tries for one ticket | 3 |
| The same checks fail twice in a row | always |
| Minutes for one try | 30 |
| Cost of one ticket | 10 USD |
| Cost of one task | 60 USD |

Then the driver asks the advisor. The advisor is a list in the settings, asked in order. The default is you. The advisor can answer a question, give one more try with a hint, give one more try with a stronger model, split the ticket, or park it.

**Where it stops.** No advisor can make the gate pass. An AI advisor decides at most 2 times for one ticket. After that, only a person decides.

## 6. Riskier changes get more checks

**What it means.** Each change gets a tier from 1 to 4 from the files it touches. A higher tier gets more checks, and you merge the riskiest changes yourself.

**Why.** A typo fix and a change to login code do not carry the same risk.

**How Tollgate does it.** No AI picks the tier. Path rules in the settings map files to tiers, and the gate works out the tier.

| Tier | When | What it adds | Who merges |
| --- | --- | --- | --- |
| 1 | At most 3 files and 50 lines, and no path rule matches | Locked tests | Tollgate, when `auto_merge` is on |
| 2 | Every other change | A plan, and a review of the change | Tollgate, when `auto_merge` is on |
| 3 | Paths you mark, such as login, payments, or user data | A security review, and an AI review on GitHub | You |
| 4 | Production settings, the test setup, the workflows, and Tollgate's own rules | The same reviews | You |

`auto_merge` is off by default. Then you merge every change.

## 7. Mistakes become rules

**What it means.** After each task, up to 3 lessons become stricter rules for the next task. Rules never get looser.

**Why.** The same mistake should not happen twice.

**How Tollgate does it.**

- `/tollgate:retro` shows a finished task's numbers and writes at most 3 lessons.
- Each lesson becomes a ticket: a new test, a new check, a new question for the reviewers, or a stricter rule.
- The gate reads the settings from the main branch, so a change cannot loosen the rules that check it.

**Where it stops.** Tollgate can make a rule stricter. Only a person can make a rule looser.

## 8. Code enforces the rules

**What it means.** Every rule above is enforced by code. A rule that is only written in a prompt does not count.

**Why.** An AI can ignore an instruction. It cannot ignore a program that refuses its work.

**How Tollgate does it.**

- The gate, the score, the stop limits, and the tiers are Python code with tests.
- The builder works in a container on a copy of your project. It has access to the AI model only: no git or GitHub credentials. It cannot send a change, create a lock, or merge.
- The driver refuses any change the builder makes under `.github/`.

**Where it stops.** Since 2026-11-21, the gate runs only on your machine. GitHub runs the tests again on every change, but no check on GitHub blocks a merge. So nothing on GitHub stops a change that skips the driver, such as a change pushed by hand. [decisions.md](decisions.md) explains why.

## 9. Plain words

**What it means.** Everything is written for people to read: docs, comments, commit messages, pull requests, and diagrams.

**Why.** A rule that nobody understands is a rule that nobody follows.

**How Tollgate does it.**

- Write like a plain-spoken senior engineer talking to someone who knows the project, in the spirit of Simplified Technical English (ASD-STE100).
- One word for each thing. [CONTEXT.md](../CONTEXT.md) lists the words.
- The writing rules are in [lenses/change.md](../lenses/change.md). `/tollgate:docs` writes by them, and a check finds the words to avoid, filler, and long dashes.
