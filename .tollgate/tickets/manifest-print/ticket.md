---
id: manifest-print
plan: e310b-10
seams: action.manifest.main, action.manifest.render
tests: tests/test_manifest_cli.py
---
## Current behavior
action/manifest.py can build, dump, and load a manifest, but has no command line. To see what a freeze tag locked, one reads the raw tag message.

## Desired behavior
`python3 -m action.manifest --repo <path> --tag <tag>` prints the manifest of that tag as plain lines: `ticket: <id>`, `commit: <sha>`, then one `file: <path>` line per locked file (sorted), then one `test: <id>` line per locked test.

## Checklist
- [C1, must] main(["--repo", r, "--tag", t]) on a tag whose message holds a manifest prints the `ticket:` line, then the `commit:` line, and returns 0.
- [C2, must] The output has one `file: <path>` line for each locked file and one `test: <id>` line for each locked test, files before tests.
- [C3, must] A tag that does not exist (checked with `git rev-parse --verify --quiet refs/tags/<tag>`, not `git tag -l`, which succeeds with empty output) returns 1, prints a non-empty message on stderr, and prints nothing on stdout.
- [C4] A tag that exists but whose message holds no manifest (no `{`) returns 1 with a non-empty message on stderr and nothing on stdout.
- [C5, must, keeps behavior] build, changed, dumps, and loads give the same results as before.

## Notes
The manifest is a dict with `ticket` (str), `commit` (str), `files` (dict path -> fingerprint) and `tests` (list of test ids, kept in written order). `loads(text)` in action/manifest.py parses a tag message into it. `main(argv)` uses argparse with `--repo` (default `.`) and `--tag` (required), and the file ends with a `__main__` guard that calls `sys.exit(main())`.

## Out of scope
JSON output, listing tags, and checking files against the tag.
