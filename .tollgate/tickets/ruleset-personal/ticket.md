---
id: ruleset-personal
plan: setup
seams: setup.apply_rulesets.wanted, setup.apply_rulesets.apply
tests: tests/test_ruleset_personal.py
---
## Current behavior
On a repository owned by a personal account, apply_rulesets fails: GitHub refuses the GitHub Actions app as a bypass actor. The tag pattern refs/tags/tg/** reaches one level only, so it misses tg/freeze/<ticket>/<n>. A second run reports "updated" because GitHub adds default fields.

## Desired behavior
A personal repository gets a tag ruleset with update and deletion rules and no bypass. The pattern reaches every tag under tg/. A second run with nothing changed reports "already in place".

## Checklist
- [C1, must] wanted("User") gives a tag ruleset with only update and deletion rules, and no bypass actors.
- [C2, must] The tag pattern is refs/tags/tg/**/*.
- [C3, must] A second apply after GitHub adds default fields reports "already in place" for both rulesets.
- [C4, must, keeps behavior] For an organization, the tag ruleset still has the creation rule and the GitHub Actions bypass.

## Out of scope
The main ruleset's rules.
