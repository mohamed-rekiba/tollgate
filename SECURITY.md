# Security

Report a security hole privately, not in a public issue.

## How to report

Open a private report on the Security tab of this repository: [report a vulnerability](https://github.com/tollgate-ai/tollgate/security/advisories/new). Say what you found, how to reproduce it, and which version you used.

## What counts

A way for an AI role, or a change that Tollgate builds, to get past a rule that the code should hold. For example:

- editing a locked test or a record in the state folder;
- reaching main without a pass record or your approval;
- reading the machine secret;
- running outside the role's isolation.

The limits that `docs/principles.md` already states, such as a person skipping the checks with `--no-verify`, are not holes.

## Threat model of session mode

Session mode stops a role's mistakes and shortcuts, such as editing locked tests, skipping checks, pushing, or touching Tollgate's state, but not a role that deliberately attacks your machine, because roles and the code they write run as you and can reach your state folder, which holds the records the gate trusts. For that, use background mode, which runs roles in a container with no state folder.

So in session mode, a role that reaches the state folder on purpose, for example from a test it writes, is a known limit, not a hole. A way for a role to get past a rule by mistake or as a shortcut is a hole. In background mode with `"isolation": "container"`, any way for a role to reach the state folder or the machine secret is a hole. Use background mode for tier 3 and 4 work from a source you do not trust.

## Versions

Only the newest release gets fixes.
