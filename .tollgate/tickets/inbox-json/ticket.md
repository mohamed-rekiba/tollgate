---
id: inbox-json
plan: e310-05
seams: setup.inbox.main
tests: tests/test_inbox_json.py
---
## Current behavior
inbox main() prints one text line per waiting question (repo#issue, title, url, tab-separated), or "Nothing waits for a person." when there are none.

## Desired behavior
With --json, main() prints the questions as one JSON list on stdout, and nothing else. Without it, output is as before.

## Checklist
- [C1, must] `main(["--repo", "o/r", "--json"], gh)` prints one JSON list whose question items have repo, issue, title, url, and returns 0.
- [C2, must] With --json and no waiting questions, it prints `[]` (not the text line).
- [C3, must, keeps behavior] Without --json, the text lines and the "Nothing waits for a person." line are unchanged.
- [C4] With --json, a repo that cannot be read appears as an item with issue null, a title starting "could not read", and no url key.
- [C5] Several --repo values give one list, in the order given.

## Tests
In tests/test_inbox_json.py, fake gh and --repo, one test per item: C1 (two questions, parsed list, keys, return 0), C2 (`[]`, return 0), C3 (text output with and without questions), C4 (GhError repo, no url key), C5 (two repos, order kept).

## Out of scope
The inbox() function, the home loading, and other commands.
