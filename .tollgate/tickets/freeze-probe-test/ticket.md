---
id: freeze-probe-test
plan: driver
seams: driver.server.GitHub.freeze
tests: tests/test_freeze_probe.py
---
## Current behavior
GitHub.freeze waits for a freeze tag, and stops early with an error when the freeze run of its ticket fails. No test covers this.

## Desired behavior
Tests lock that behavior in.

## Checklist
- [C1, must, keeps behavior] A failed freeze run of the same ticket stops the wait with an error.
- [C2, must, keeps behavior] A failed freeze run of another ticket does not stop the wait.
- [C3] The error names the run.

## Out of scope
The plan lock.
