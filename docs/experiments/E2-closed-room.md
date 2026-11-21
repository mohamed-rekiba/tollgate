# E2: The closed room

**Result: not run.**

## Why

The workspace that built this repository has a container command but no container daemon, and it must not use its own model access as Tollgate's builder.

## What the owner runs

[scripts/e2_closed_room.sh](scripts/e2_closed_room.sh) on a machine with Docker or Podman and Claude Code. It makes a fresh copy of a repository, starts Claude Code in a container with only the model key, asks it to add one line to a file, and checks three things:

1. The output parses as data and holds a cost.
2. The file changed in the copy.
3. A `git push` from inside the container fails.

## What rests on this experiment

The builder's container in task 2.3, and the claim that the builder cannot reach the server. Until E2 passes, the driver treats `sandbox: container` as untested, and the plan lists it under "Not verified".
