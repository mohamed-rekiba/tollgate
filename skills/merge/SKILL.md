---
name: merge
description: Merge a ready Tollgate change into main. It lists the changes that passed the gate, shows one, asks you to approve tier 3 and 4, and merges it. Use when the user runs /tollgate:merge or asks to merge, approve, or review what is ready.
---

# Merge a ready change

`TG` is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -P -m setup.merge`, from the project folder.

Words: a **ready change** is a commit that passed the gate and is not on main yet. Its **pass record** is the gate's result. A change of tier 3 or 4 also needs your **approval**: a record you write by typing `yes` in your own terminal. A **change made by hand**, such as the branch `tollgate-sync` that a home writes, has no pass record: it needs your approval at any tier. `<commit>` below may be a branch name.

## 1. List the ready changes

Run `python3 -m setup.merge list`. Show each line: the commit, the ticket, the tier, the score, the branch, and whether it needs an approval. If the user named a change, go to step 2 with it. Otherwise ask which one, in one question.

Done when the user has picked a change, or there is none.

## 2. Show it

Run `python3 -m setup.merge show <commit>`. Show the checks, the commits, and the files it changes. For tier 3 and 4, offer to show the diff: `git diff main...<commit>`.

## 3. Approve it, for tier 3 and 4 and a change made by hand

You never approve. Only the user does, by typing `yes` in their own terminal. The command refuses to run when its input is not a terminal.

Ask the user to run this in their terminal, with the `!` prefix in this session or in a terminal of their own:

```sh
! PYTHONPATH="$TG" python3 -P -m setup.merge approve <commit>
```

Write out `$TG` as the full path in the line you give them. It shows the change and asks the user to type `yes`.

Done when the command prints `approved:`.

## 4. Merge it

Run `python3 -m setup.merge merge <commit>`. The store merges it into main with a merge commit, and pre-commit checks the pass record and the approval again.

Done when it prints `merged:` and the merge commit. Tell the user the commit in one line.
