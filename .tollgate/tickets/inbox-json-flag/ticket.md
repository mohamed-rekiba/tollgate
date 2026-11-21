---
id: inbox-json-flag
plan: e310b-05
seams: setup.inbox.main
tests: tests/test_inbox_json_flag.py
---
## Current behavior
`inbox` prints one text line per question, or "Nothing waits for a person." when there are none.

## Desired behavior
With `--json`, it prints the questions as one JSON list on stdout instead of text lines.

## Checklist
- [C1, must] `main(["--repo", "o/r", "--json"], gh)` prints one JSON list whose items have the keys repo, issue, title, url.
- [C2, must] With `--json` and no questions, stdout is `[]`, not the "Nothing waits" text.
- [C3, must, keeps behavior] Without `--json`, the text lines and the "Nothing waits" message are unchanged.
- [C4] A repo that could not be read shows in the JSON list as an item with issue null.

## Out of scope
Other flags, and the `inbox()` function itself.
