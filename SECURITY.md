# Security

Report a security hole privately, not in a public issue.

## How to report

Open a private report on the Security tab of this repository: [report a vulnerability](https://github.com/tollgate-ai/tollgate/security/advisories/new). Say what you found, how to reproduce it, and which version you used.

## What counts

A way for an AI role, or a change that Tollgate builds, to get past a rule that the code should hold. For example:

- editing a locked test or a signed record;
- reaching main without a pass record or an owner's approval;
- reading the machine's keys;
- running outside the role's isolation.

The limits that `docs/principles.md` already states, such as a person skipping the checks with `--no-verify`, are not holes.

## The machine key in session mode

In session mode, the default, each role runs as a subagent of your own Claude Code session, on your machine. The hook refuses a role's Read, Grep, or Glob of the key folder, or of the state folder outside its copy, and a Bash command whose text names either folder. A Bash command can still hide a path, for example by building it from parts. So in session mode the machine key is protected by the hook only.

The background driver with `"isolation": "container"` is the mode where the key is out of a role's reach: the key folder is never mounted in the container. Use it when a role must have no way to the machine key. A way around the hook in session mode is a known limit, not a hole; a way around it in background mode with a container is a hole.

## Versions

Only the newest release gets fixes.
