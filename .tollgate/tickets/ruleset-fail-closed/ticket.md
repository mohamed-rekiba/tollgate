---
id: ruleset-fail-closed
plan: setup
seams: setup.apply_rulesets.apply, setup.apply_rulesets.main
tests: tests/test_ruleset_fail_closed.py
---
## Current behavior
apply_rulesets treats a repository as a personal account when GitHub's answer has no owner type, which gives the weaker tag ruleset. It crashes when that answer is empty. The --print output always shows the rules for an organization.

## Desired behavior
An unknown owner type counts as an organization, so the stricter rules are asked for and GitHub rejects them if they do not fit. An empty answer does not crash. --print reads the owner type and prints the rules that apply will create.

## Checklist
- [C1, must] apply asks for the creation rule when GitHub's answer has no owner type.
- [C2, must] apply does not crash when GitHub's answer for the repository is empty.
- [C3, must] --print for a personal repository prints no creation rule.
- [C4, must, keeps behavior] apply for a personal repository asks for no creation rule.

## Out of scope
The comparison of rulesets.
