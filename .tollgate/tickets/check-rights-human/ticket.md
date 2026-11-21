---
id: check-rights-human
plan: e310-09
seams: check_rights.sentence, check_rights.main
tests: tests/test_check_rights_human.py
---
## Current behavior
`python -m setup.check_rights owner/name` always prints one JSON object such as `{"level": "admin", "reason": "you can set rulesets"}`.

## Desired behavior
With `--human` it prints one plain sentence, `<level>: <reason>.`, for example `admin: you can set rulesets.` Without the flag the output is the same JSON as before. Exit codes do not change.

## Checklist
- [C1, must] `sentence({"level": "admin", "reason": "you can set rulesets"})` returns `admin: you can set rulesets.`
- [C2, must] `main([repo, "--human"], gh)` prints exactly that one sentence line (not JSON) and returns 0 for admin, write and copy levels.
- [C3, must] When the level is none (no write access), `--human` prints `none: <reason>.` and returns 1.
- [C4] When the GitHub call fails with GhError, `--human` prints `none: <error text>.` and returns 1; no sentence ends with two periods.
- [C5, must, keeps behavior] Without `--human`, `main` prints the same JSON as before and returns the same codes.

## Out of scope
Other scripts in setup/, and the wording of the reasons in `level`.
