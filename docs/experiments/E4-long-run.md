# E4: A long run from a skill

**Result: partly run.**

## What was run

A shell started a script with `setsid -f`, then exited. The script kept writing one line every two seconds. It had a new session id and its parent was process 1.

## What was not run

Closing a Claude Code session after a skill starts the driver. The owner runs [scripts/e4_long_run.md](scripts/e4_long_run.md).

## What this changes in the plan

The task skill starts the driver with `setsid -f` and redirects all three standard streams. The driver writes its process id to a file, so the status skill can tell a running driver from a dead one.
