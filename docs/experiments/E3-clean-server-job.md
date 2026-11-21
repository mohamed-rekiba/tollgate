# E3: The clean server job

**Result: run. The plan was wrong about which copy of a workflow runs.**

## What was run

A workflow on `main` listened to both `pull_request` and `pull_request_target`. Its job name said `from-main`. Pull request 2 edited the same file to say `from-branch`.

## What happened

| Event | Job that ran |
| --- | --- |
| `pull_request` | `e3 pull_request from-branch` |
| `pull_request_target` | `e3 pull_request_target from-main` |

For a `pull_request` event, GitHub runs the copy of the workflow from the pull request. A change can therefore rewrite the workflow that checks it. For `pull_request_target`, GitHub runs the copy from the base branch.

## What this changes in the plan

1. The gate workflow runs on `pull_request_target`. It checks out the change into a folder, puts back the harness from `main` and the locked tests from the freeze, and runs the checks with a token that can only read.
2. A change to any file under `.github/` is harness, so it is tier 4 and needs an approval by a person.
3. A change could still add its own workflow with a job of the same name as the gate, and that job would pass. Whether a required check then counts as passed is not known. The ruleset should require the gate check from the GitHub Actions app, and the owner should test the case: see [scripts/e3_fake_check.md](scripts/e3_fake_check.md).

## What was not run

Running the tests of the change in a job with no secrets while the harness comes from `main`. That is built and tested as part of task 1.7.
