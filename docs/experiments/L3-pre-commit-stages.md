# L3: when pre-commit runs

**Result: passed, with one limit.** Run on 2026-11-22 with pre-commit 4 and git 2.43.

## The question

pre-commit is the git layer of Tollgate. On which git steps do its checks run?

## What was run

A scratch repository with one local hook in four stages: `pre-commit`, `commit-msg`, `pre-merge-commit`, and `pre-push`. Each run appended a line to a log.

| Step | Checks ran |
| --- | --- |
| Commit | Yes: `pre-commit` and `commit-msg` |
| Merge with `--no-ff` | Yes: `pre-merge-commit` and `commit-msg` |
| Fast-forward merge | No |
| Push | Yes: `pre-push` |

## What follows

A fast-forward merge skips every check. So every merge into `main` creates a merge commit, and the store is the only path that merges. A Claude Code hook stops Claude from merging any other way.
