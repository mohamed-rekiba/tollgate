# Decisions

Each decision here holds for Tollgate as it is built. Each one says what was decided, why, and where it stops.

## Everything runs on your machine

**Decision.** Tollgate runs on your machine. No product file calls GitHub, `gh`, or any outside service, except the AI model through Claude Code.

**Why.** A check that lives on a hosted service depends on rights you may not have, and on rules that service may change. On your machine, the store, the gate, and pre-commit need nothing but git, Python, and `ssh-keygen`.

**Limit.** Nothing outside your machine checks a change. A person who skips pre-commit with `--no-verify` can change main by hand.

## Two layers, and the signed records behind them

**Decision.** Two layers enforce the rules: Claude Code hooks and policies, then pre-commit in git. The gate and the signed records are the real checks.

**Why.** A hook stops a bad tool call early, with a reason the role can read. pre-commit stops a bad commit, merge, or push, whoever makes it. Neither is complete alone: a hook reads only the text of a Bash command, and pre-commit can be skipped. A signed record cannot be faked without the machine key, so the store and the pre-commit checks can trust it.

**Limit.** The hook and the policies are untested inside Claude Code (L1). pre-commit does not run on a fast-forward merge (L3), so the store always merges with a merge commit.

## The state folder lives outside the project

**Decision.** The store keeps every record in a state folder outside the project: `~/.local/state/tollgate/<name>-<hash>/` on Linux, `~/Library/Application Support/tollgate/<name>-<hash>/` on macOS. The machine key lives in `~/.config/tollgate/`.

**Why.** A role works in a copy of the project. It cannot reach a folder that is outside its copy and never mounted into its container. The hash of the project's path keeps two projects with the same name apart.

**Limit.** A role that runs with no isolation runs as you, and you can write the state folder. The signatures, not the folder, are what a role cannot fake.

## Records are signed with SSH keys

**Decision.** The store signs each lock, plan lock, and pass record with the machine key, through `ssh-keygen -Y sign`. Each kind of record has its own namespace: `tollgate-lock`, `tollgate-plan`, `tollgate-pass`, `tollgate-approval`. A record is JSON with sorted keys, and the signature covers its exact bytes.

**Why.** `ssh-keygen` is on every machine with git, and it needs no library. A namespace stops a signature for one kind of record from passing as another: a pass record cannot pose as an approval.

**Limit.** Anyone who holds the machine key can sign a record. The key folder is never mounted into a role's container.

## Keys are read from main, never from the change

**Decision.** The store and the checks verify a lock, a plan lock, or a pass record against `signers` in the settings on main. They verify an approval against `owners` on main.

**Why.** A change that adds its own key to the settings must not be able to approve itself.

**Limit.** A key that is on main is trusted until a person removes it.

## Only an owner approves

**Decision.** An approval is a record that an owner signs with their own SSH key, with `/tollgate:merge`. `init` refuses an owner key that is the machine key.

**Why.** The AI never approves its own work. The machine key signs pass records, and it is never in `owners`, so it can never approve. `ssh-keygen` asks for the passphrase in your terminal, where no role can type.

**Limit.** An owner key with no passphrase can be used by any program that runs as you.

## The store is the only path that merges

**Decision.** The store merges a ready change into main with `git merge --no-ff`. It refuses a commit with no verified pass record, a tier 3 or 4 change with no approval, and a pass record for a lock that is not the current one. The hook refuses a merge into main from a role or from your own Claude Code session.

**Why.** A merge commit makes pre-commit run (L3), so the pre-commit check sees the pass record again. One path to merge means one set of rules.

**Limit.** `auto_merge` is off by default, so you merge every change. With it on, the driver merges only tier 1 and 2.

## A change made by hand needs an approval

**Decision.** A commit with no ticket and no pass record merges only with an owner's approval that names no ticket. The store treats it as tier 4.

**Why.** A change made by hand has no locked tests, so the gate cannot pass it. A person vouches for it instead. An AI ticket always needs a pass record.

**Limit.** The setting `free` lists paths that should need no ticket, such as `docs/**`. No code reads it, so a change to docs by hand also needs an approval.

## Isolation is a container by default

**Decision.** `"isolation": "container"` runs each role in Docker, with only its own copy mounted, read-only for a reviewer and the advisor. Only the model access variables go in, by name. `"isolation": "sandbox"` runs Claude Code with its own sandbox and the role's policy instead.

**Why.** A hook reads only the text of a command, so `python -c` can write a file that a rule forbids. A container that mounts only the copy stops that write. The sandbox may stop it too, but L2 did not run.

**Limit.** You name the container image under `container_image`. Tollgate ships none. A real run through the local driver is untested.

## The gate uses no AI

**Decision.** The gate is a program that reads git, the lock, the plan lock, and the check results. A reviewer's verdict reaches it only as a fact for tier 3 and 4.

**Why.** An AI gate can differ from run to run, and a change can talk it into a pass.

**Limit.** The gate trusts the test report that the checks write. Code written to forge its own test results is out of scope.

## Every must-have item has a locked test

**Decision.** The test writer writes one test at a seam for each must-have item, before any code. The store locks it only when none of the new tests passes yet, except an item marked `keeps behavior`.

**Why.** A test gives the same answer each time. A test that passes before the build tests nothing new.

**Limit.** A locked test can be wrong. The store allows one replacement lock, but the driver has no step that asks for one.

## The tier comes from the files

**Decision.** `gate/tiers.py` works out the tier from the files a change touches and the path rules on main. Harness is always tier 4. The built-in harness list includes `.tollgate/settings.json`, `.tollgate/lenses/**`, `.tollgate/checks/**`, `.pre-commit-config.yaml`, and the settings files of common test tools. The settings can add to it and cannot remove from it.

**Why.** A builder that picks the tier of its own work can pick a low one.

**Limit.** A risky path with no rule counts as tier 1 or 2.

## The driver is a script, and a skill only starts it

**Decision.** `/tollgate:task` starts `driver.task` or `driver.roadmap` as its own process with `setsid -f`, and returns. The driver writes one log line for each event, in the state folder. A driver that starts again reads the log and repeats no finished step.

**Why.** An AI session loses its place on a run of hours. A script gives the same result each time.

**Limit.** The machine must stay on while a task runs.

## A question waits in the state folder

**Decision.** When the driver needs a person, the store writes a question in `questions/<n>.json`. You answer with `/tollgate:inbox`, for example `tollgate decide retry keep the retries short`.

**Why.** A question in a file needs no outside service, and the driver reads the answer when it starts again. A question never blocks the other tickets.

**Limit.** Nothing tells you that a question waits. `/tollgate:status` and `/tollgate:inbox` show it when you ask.

## Python with the standard library only

**Decision.** Tollgate is Python 3.11 with the standard library only. The checks that pre-commit runs are single files, copied into `.tollgate/checks/`.

**Why.** A guard with dependencies can break when a dependency changes. A copied check runs with no Tollgate code, so the project carries its own.

**Limit.** A copied check can fall behind the plugin. `setup/health.py` warns when a copy differs.

## The words of one ticket

These formats hold for every ticket:

- The branch of a ticket is `tg/<ticket id>`. The branch of a plan is `tg-plan/<task id>`.
- The header of a ticket is plain `key: value` lines between two `---` lines. The keys are `id`, `plan`, `seams`, and `tests`.
- A checklist line is `- [C1, must] text`. A test belongs to the item whose id is in its name, such as `test_c1_retries_twice`.
- The one test report format is JUnit XML. A test id is `<classname>::<name>`.
- Two tries failed the same way when the failed checks and the failed locked tests are the same, or the same items failed at the same score.
