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

## Versions

Only the newest release gets fixes.
