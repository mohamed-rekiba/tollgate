---
id: human-flag
plan: e310b-09
seams: check_rights.sentence, check_rights.main
tests: tests/test_check_rights_human.py
---
## Current behavior
check_rights.py always prints one JSON object, such as {"level": "admin", "reason": "you can set rulesets"}.

## Desired behavior
With `--human` it prints one plain sentence, "<level>: <reason>.", for example "admin: you can set rulesets." Without the flag the output is the same JSON as now.

## Checklist
- [C1, must] sentence({"level": "admin", "reason": "you can set rulesets"}) returns "admin: you can set rulesets."
- [C2, must] main([repo, "--human"], gh) prints exactly that sentence on one line, not JSON, for an admin.
- [C3, must, keeps behavior] main([repo], gh) without the flag still prints the same JSON and the same return code.
- [C4] With --human and a GhError from the repository lookup, main prints "none: <error text>." and returns 1.
- [C6, must] sentence() gives "write: you can push but cannot set rulesets.", "copy: the repository allows only local actions." and "none: you have no write access." for the dicts level() returns for those levels.
- [C5] The return code with --human is 0 for admin, write and copy, and 1 for none.

## Out of scope
Other scripts in setup/, and changes to level().
