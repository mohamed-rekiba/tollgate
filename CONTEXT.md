# Tollgate

Tollgate keeps a change written by an AI out of the main branch until tests that were locked before the build pass on GitHub.

## Language

### Work

**task**: What a person asks for, and the work Tollgate does for it. The person's own words for it are the request.
_Avoid_: user story, epic

**plan**: The design for a task. It names every file that changes, every seam, and every ticket.
_Avoid_: design doc, PRD

**ticket**: One small part of a plan, sized for one AI session. It has an id.
_Avoid_: user story, work item

**checklist**: The list on a ticket that says what done means. Each line is an item.
_Avoid_: acceptance criteria, requirements

**must-have item**: A checklist item that cannot fail. Each one has a locked test.
_Avoid_: required item, critical item

**seam**: A public point where a test observes behavior: a web address, a command, the name and inputs of a function.
_Avoid_: boundary, touchpoint

**attempt**: One builder session, then one run of the gate.
_Avoid_: iteration

**score**: The share of checklist items that passed, as a percentage.
_Avoid_: rating, grade

### Roles

**role**: One job for an AI session: builder, test writer, reviewer, or advisor.
_Avoid_: agent, persona

**builder**: The role that writes plans, tickets, and code.
_Avoid_: implementer, coder, developer

**test writer**: The role that writes one locked test at a seam for each must-have item, before the builder builds.
_Avoid_: tester, QA

**reviewer**: The role that reads something through one lens and reports findings. It has no history and cannot edit.
_Avoid_: critic, judge, goldfish

**lens**: A file that tells a reviewer what to look for.
_Avoid_: rubric

**finding**: One problem that a reviewer or a check reports: blocking, major, or minor.
_Avoid_: defect, nit

**advisor**: Whoever makes a decision that the loop cannot make: a person, or an AI on a different model from the builder.
_Avoid_: approver, human in the loop, escalation

### Proof

**checks**: Commands that pass or fail with no AI: tests, style, types, a scan for secrets.
_Avoid_: linters, validators

**harness**: The files that decide how tests run: test settings, shared test helpers, dependency lists, the server workflows.
_Avoid_: test config, test infrastructure

**freeze**: The point after which a ticket and its tests cannot change. GitHub creates it as a tag.
_Avoid_: lock-in, snapshot

**manifest**: The record of a freeze: each frozen file with its fingerprint, and the name of each frozen test.
_Avoid_: lockfile, inventory

**gate**: The check that decides whether a change may merge. It uses no AI.
_Avoid_: judge, verifier, quality gate

**tier**: A number from 1 to 4 that says how much a change puts at risk. The gate works it out from the files that changed.
_Avoid_: risk level, severity

### Parts

**driver**: The Tollgate script that runs the steps of a ticket in order.
_Avoid_: orchestrator, runner

**log**: A file on the person's machine. The driver adds one line for each event.
_Avoid_: journal

**report**: The file that the driver writes from the logs when a task ends.
_Avoid_: summary

**retro**: The look back at a finished task: its numbers, and at most 3 lessons, each written as a ticket.
_Avoid_: postmortem, retrospective

**skill**: A set of instructions that Claude Code follows when a person types its name.
_Avoid_: slash command

**plugin**: The package that adds Tollgate to Claude Code.
_Avoid_: extension, add-on

**workflow**: The one GitHub workflow, `tollgate.yml`, that runs the freeze, the plan lock, the tests, the review, and the gate. It reads which version of Tollgate to run from the settings on main.
_Avoid_: Action, pipeline

**home**: An optional git repository that holds many projects as submodules.
_Avoid_: ops repo, workspace, portfolio

**GitHub**: Where the locked tests, the workflow, the gate, and the main branch live. The AI cannot change anything there.
_Avoid_: the server, remote
