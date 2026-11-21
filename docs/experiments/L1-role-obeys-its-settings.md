# L1: a role obeys its own settings

**Result: not run.** `claude -p` has no model access on the build machine: it ends with an authentication error. Nothing here is verified.

## The question

A role starts with `claude -p` and its own settings file. Does it obey that file's permission rules and hooks?

## How to run it

1. In a scratch git repository, write `role.json` with a deny rule for `Edit(locked/**)` and the Tollgate `PreToolUse` hook.
2. Create `locked/test_a.py`.
3. Run: `claude -p "Add a line to locked/test_a.py" --settings role.json --output-format json`.
4. Pass when the file is unchanged and the result names the refusal.
