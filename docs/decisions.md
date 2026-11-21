# Decisions after stage 0

Two fresh reviewers read the plan with the results of the experiments (task R0). This file records each decision that answers their findings (task D0). The plan in [plan.md](plan.md) is changed to match where a decision changes it.

## How the freeze starts

- The driver pushes the ticket file and its tests to the branch `tg/<ticket id>`.
- The driver starts the freeze workflow by hand (`workflow_dispatch`) on the main branch, with the input `ticket`. It uses your own access.
- Job one has a token that can only read and no secrets. It checks out the head of `tg/<ticket id>`, puts back the harness from the main branch, runs the check named `tests`, and uploads the test report.
- Job two runs none of the code. It downloads the report, builds the manifest, writes its own run id into the manifest, and creates the tag `tg/freeze/<ticket id>/<number>` on the commit it froze.

## How the gate trusts a freeze

The gate takes the freeze with the highest number. It accepts it when all of these hold:

1. The tag points at the commit that the manifest names.
2. The manifest names the ticket of the branch.
3. The run named in the manifest used the workflow file `.github/workflows/tollgate-freeze.yml`, ran on the main branch, was started by hand, and succeeded.
4. The title of that run is `tollgate freeze <ticket id>`, so the run froze this ticket.
5. The run recorded the same manifest as the tag. The lock job uploads the tag message as the artifact `tollgate-manifest`, and only that run can upload to itself.
6. The number in the tag name is plain ASCII digits and equals the number in the manifest.

A tagger name proves nothing, because anyone with write access can set one. Points 3 to 5 are what a forged freeze cannot meet. The artifact expires after 90 days. A pull request that waits longer needs a new freeze.

## What a ticket may lock

A ticket's `tests:` header may not name harness or a tier 3 or 4 path. The freeze refuses it. If such a file is frozen anyway, it still counts for the tier, and the restore step keeps the main branch's copy.

## Tag creation on a personal account

GitHub accepts the GitHub Actions app as a bypass actor only in an organization. On a personal account, the tag ruleset blocks moving and deleting `tg/` tags, but not creating them. A forged tag still fails the gate: its run id names no run of the freeze or plan workflow that recorded the same manifest.

## The admin bypass

The ruleset on the main branch lets a repository admin merge a pull request that the gate blocks, and GitHub logs it. It is for emergencies only. No normal change needs it: an upgrade is a settings change, a change under `.github/` is tier 4 and takes an approval, and a broken review never blocks an approval. The driver never uses it.

## One workflow, and the version in the settings

The four workflow files became one, `tollgate.yml`, that is the same for every version of Tollgate. The version is `"version"` in the settings on main: a full commit id, or `"self"` in the Tollgate repository, where main's own code runs the gate. Before this, each workflow held a pin, so every upgrade was a `.github/` change, and each one needed the admin bypass.

## Nothing can deadlock

- A change under `.github/` is tier 4, not an automatic failure.
- For tier 4, the review is advice. A person's approval decides.
- For tier 3, the review passing or a person's approval is enough.
- Changes to free paths only, such as docs, need no ticket.

So every change can merge through the gate with at most one approval by a person.

## Which approvals count

A review counts only from someone whose role in the repository is owner, member, or collaborator, or who is named under `approvers`.

## Where the ticket id comes from

The branch name: `tg/<ticket id>`. A pull request from any other branch fails gate rule 1.

## Test reports and test ids

- The one report format is JUnit XML.
- A test id is `<classname>::<name>`.
- A test belongs to a ticket's test file when its `file` attribute is that path, or when its class name, with dots read as folders, names that file without its extension.
- A test case with a `skipped` child is skipped. One with a `failure` or `error` child failed. Any other passed.

## Checklist items and tests

- Each checklist line carries an id: `- [C1, must] text`.
- A test belongs to the item whose id appears in its name, such as `test_c1_retries_twice`.
- The freeze refuses a test that names no item, and refuses the ticket if a must-have item has no test.

## The ticket header

Plain `key: value` lines between two `---` lines, with lists written with commas. The standard library reads it with no YAML library. The keys are `id`, `plan`, `seams`, and `tests`. `tests` lists every file the locked tests need: the test files and any helper or data file they load. The freeze locks all of them.

## Harness that a project cannot shorten

These count as harness in every project, whatever the settings say: `.github/**`, `.tollgate/settings.json`, `.tollgate/lenses/**`, and the settings files of common test tools, such as `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`, `tox.ini`, `package.json`, `jest.config.*`, `vitest.config.*`, `go.mod`, `Cargo.toml`, `requirements*.txt`, and lock files. The settings can add to this list and cannot remove from it.

## Changes under .github

The driver refuses to push any change under `.github/`, because a file there that a pushed branch adds runs with the repository's rights before any gate runs. A person's change under `.github/` is harness, so it is tier 4 and needs an approval.

## Approval by a person

- A review with the state "approved" by someone other than the author, on the latest commit.
- Or a comment that reads exactly `tollgate approve <full id of the latest commit>`, by a user named under `approvers` in the settings on the main branch, whose account type is User.

A comment cannot name a commit before the commit exists, so it comes after the latest push.

## Plan tags in stages 1 and 2

The plan tag arrives in stage 3. Until then, `require_plan` is off in the settings, and gate rule 2 passes with the note "no plan required". With `require_plan` on and no plan tag, rule 2 fails.

## How results reach the gate

The gate workflow runs only for pull requests into the main branch, and it checks out the main branch by name. The action starts Python with `-P`, so a module in the change cannot replace the gate's code. Any error inside the gate posts a failing check.

The gate does not run checks. A caller runs them with `action/checks.py`, writes the results to a file, and passes the file to the gate. The gate workflow does this on the server. The driver does it on your machine.

## The contract with Claude Code

- The driver runs the command from the settings, for example `claude -p`, with `--output-format json` and `--allowedTools <list>`, and sends the prompt on standard input.
- The prompt is the role file, then the inputs as JSON.
- The driver reads the fields `result` and `total_cost_usd` from the output.
- The role ends its answer with one JSON object in a fenced block. The driver reads the last such block.
- A fake role is any command that reads the prompt on standard input and prints the same JSON shape.

## Locks and the log

- One file holds one log. The driver appends one JSON line for each event and holds an exclusive file lock while it writes.
- A ticket lock is a file created only if it does not exist, holding the process id. A lock whose process is gone is stale and is taken over.

## "The same checks failed"

Two attempts failed the same way when the names of the failed checks and the ids of the failed locked tests are the same in both.

## Still open, for the owner

- E1, the ruleset part: [experiments/scripts/e1_rulesets.sh](experiments/scripts/e1_rulesets.sh).
- E2, the container: [experiments/scripts/e2_closed_room.sh](experiments/scripts/e2_closed_room.sh).
- E3, a fake check with the gate's name: [experiments/scripts/e3_fake_check.md](experiments/scripts/e3_fake_check.md). Tollgate's own defense is that the driver never sends a change under `.github/`. A person who adds such a file can still fake the check. If GitHub counts the fake check as passed, the fallback is a second required check that a pull request cannot add: the review workflow, which then also runs for tier 1 and 2.
- E4, a driver that outlives a closed session: [experiments/scripts/e4_long_run.md](experiments/scripts/e4_long_run.md).
