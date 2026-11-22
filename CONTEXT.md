# Tollgate

Tollgate keeps a change written by an AI out of the main branch until the gate, on your machine, sees tests that were locked before the build pass.

## Language

### Work

**task**: What a person asks for, and the work Tollgate does for it. The person's own words for it are the request.
_Avoid_: user story, epic

**roadmap**: An ordered list of tasks, for a request too large for one plan: the base, the skeleton, then the features. It has its own checklist.
_Avoid_: backlog, milestone plan

**analysis**: What the analyst found in the project before the plan, in six sections. Each fact is confirmed, with a citation to the code, or assumed.
_Avoid_: survey, discovery, research

**citation**: The code that proves a fact: `[path:line]` or `[path::name]`. The driver checks that it exists.
_Avoid_: source link

**plan**: The design for a task. It names every file that changes, every seam, the code it reuses, the risks, the assumptions, and every ticket.
_Avoid_: design doc, PRD

**assumption**: A point that the request and the analysis do not settle, listed in the plan and asked as a question that ends with a question mark. A plan with one waits for the advisor.
_Avoid_: open question

**ticket**: One small part of a plan, sized for one AI session. It has an id.
_Avoid_: user story, work item

**checklist**: The list on a ticket that says what done means. Each line is an item.
_Avoid_: acceptance criteria, requirements

**must-have item**: A checklist item that cannot fail. Each one has a locked test.
_Avoid_: required item, critical item

**seam**: A public point where a test observes behavior: a web address, a command, the name and inputs of a function.
_Avoid_: boundary, touchpoint

**try**: One builder session, then one run of the gate. The driver starts each try from the best try so far.
_Avoid_: attempt, iteration

**score**: The share of checklist items that passed, as a percentage. A try needs 70 or more.
_Avoid_: rating, grade

### Roles

**role**: One job for an AI session: analyst, builder, test writer, reviewer, or advisor.
_Avoid_: agent, persona

**analyst**: The role that reads the project before the plan and writes the analysis. It can only read.
_Avoid_: explorer, scout

**builder**: The role that writes plans, tickets, and code.
_Avoid_: implementer, coder, developer

**test writer**: The role that writes one locked test at a seam for each must-have item, before the builder builds.
_Avoid_: tester, QA

**reviewer**: The role that reads something through one lens and reports findings. It has no history and cannot edit.
_Avoid_: critic, goldfish

**lens**: A file that tells a reviewer what to look for.
_Avoid_: rubric

**finding**: One problem that a reviewer or a check reports: blocking, major, or minor.
_Avoid_: defect, nit

**advisor**: Whoever makes a decision that the loop cannot make: a person, or an AI on a different model from the builder. The settings list the advisors in order.
_Avoid_: human in the loop, escalation

**checkpoint**: A place where the advisor decides whether the task goes on: after the plan, after each ticket, or after the whole task. The setting `checkpoints` lists them.
_Avoid_: approval step

**owner**: A person whose SSH public key is in `owners` in the settings on main. Only an owner signs an approval.
_Avoid_: admin, maintainer

### Proof

**checks**: Commands that pass or fail with no AI: tests, style, types, a scan for secrets. They are the project's own tools.
_Avoid_: linters, validators

**harness**: The files that decide how tests run: test settings, shared test helpers, dependency lists, the pre-commit config, Tollgate's settings and checks.
_Avoid_: test config, test infrastructure

**lock**: The signed record of a ticket's tests, made before any code: each locked file with its fingerprint, and the name of each locked test. A ticket has at most 2 locks: the first, and one replacement.
_Avoid_: freeze, snapshot

**plan lock**: The signed record of an approved plan: the fingerprint of the plan and of each of its tickets.
_Avoid_: plan tag, plan freeze

**gate**: The program that decides whether a try passes. It uses no AI, and the driver runs it on your machine after each try.
_Avoid_: verifier, quality gate

**tier**: A number from 1 to 4 that says how much a change puts at risk. The gate works it out from the files that changed.
_Avoid_: risk level, severity

**pass record**: The signed record that a commit passed the gate: its ticket, tier, score, the checks, and the fingerprint of its lock.
_Avoid_: pass token, green build

**approval**: The record an owner signs with their own SSH key to let a tier 3 or 4 change, or a change made by hand, merge.
_Avoid_: sign-off, LGTM

**ready change**: A branch whose last commit has a pass record and is not on main yet. It waits for a merge.
_Avoid_: pull request, candidate

**signers**: The public keys in the settings on main that may sign locks, plan locks, and pass records. Each is the machine key of a machine that runs Tollgate.
_Avoid_: trusted keys, keyring

**machine key**: The SSH key that Tollgate makes on your machine, in the key folder. It signs locks, plan locks, and pass records. It never signs an approval.
_Avoid_: bot key, service key

### Parts

**driver**: The Tollgate program that runs the steps of a task and of each ticket in order, on your machine.
_Avoid_: orchestrator, runner

**store**: The part of Tollgate that keeps its state. The driver, the gate, and the skills reach the state folder only through it. It locks tests, signs records, asks questions, and merges.
_Avoid_: repository layer, backend

**state folder**: The folder outside the project where the store keeps the locks, the pass records, the approvals, the questions, the builder's copies, and the logs. No role can write there.
_Avoid_: data dir, cache

**copy**: The builder's own clone of the project, in the state folder, with no remote. A role works only there.
_Avoid_: workspace, checkout

**session mode**: The default way to run the roles: your own Claude Code session runs each role as one of Tollgate's subagents, one step at a time, while the driver decides every step.
_Avoid_: interactive mode

**background mode**: The other way to run the roles: the driver starts each role as its own process, in its isolation, and keeps running after you close Claude Code.
_Avoid_: daemon mode, headless mode

**step**: In session mode, one role the driver needs, with its prompt and its key, written to the step file `run/step.json` in the state folder.
_Avoid_: job

**isolation**: How the background driver keeps a role apart from the rest of your machine: `container` (Docker, the default) or `sandbox` (Claude Code's own sandbox).
_Avoid_: closed room, jail

**hook**: A command that Claude Code runs before each tool call. Tollgate's hook refuses a call that breaks a rule.
_Avoid_: interceptor

**policy**: The Claude Code settings file that Tollgate writes for each role: its permission rules, the sandbox, and the hook.
_Avoid_: profile, permission set

**pre-commit**: The tool that runs Tollgate's checks in git, before each commit, merge, and push.
_Avoid_: git hooks layer

**question**: A decision that waits for a person, in the state folder. You answer it with `/tollgate:inbox`.
_Avoid_: ticket comment

**log**: A file in the state folder. The driver adds one line for each event.
_Avoid_: journal

**report**: The file that the driver writes from the logs when a task ends.
_Avoid_: summary

**retro**: The look back at a finished task: its numbers, and at most 3 lessons, each written as a ticket.
_Avoid_: postmortem, retrospective

**skill**: A set of instructions that Claude Code follows when a person types its name.
_Avoid_: slash command

**plugin**: The package that adds Tollgate to Claude Code.
_Avoid_: extension, add-on

**home**: An optional git repository on your machine that holds many projects as submodules, and the rules they share.
_Avoid_: ops repo, portfolio
