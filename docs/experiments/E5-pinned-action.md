# E5: Pin the Action

**Result: run, passed.**

## What was run

Branch `tg-lab/e5-action` added an action in the folder `lab-action/` at commit `e2f7f20`. A later commit changed the action so that it fails, and added a workflow that calls `tollgate-ai/tollgate/lab-action@e2f7f20`.

## What happened

The check `e5 pinned action` passed. The workflow ran the pinned copy, not the changed one.

## What this changes in the plan

Nothing. A project can pin the Action in the folder `action/` of this repository to one exact commit.

Not tested: a workflow in a different repository calling this private repository's action. GitHub allows that only when the repository's Actions settings share it. A public release of Tollgate removes the question.
