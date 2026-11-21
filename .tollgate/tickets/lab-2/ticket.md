---
id: lab-2
plan: lab
seams: lab.shout.shout, action.paths.matches
tests: tests/test_lab_2.py
---
## Current behavior
There is no shout function.

## Desired behavior
lab.shout.shout returns its text in capitals.

## Checklist
- [C1, must] shout("ann") returns "ANN".
- [C2, must, keeps behavior] matches("a/b.py", ["a/**"]) still returns True.
- [C3] shout has a docstring.

## Out of scope
Everything else. This ticket exists only to prove the gate.
