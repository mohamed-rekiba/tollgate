---
id: ticket-file-cli
plan: e310b-01
seams: action.tickets.main, python3 -m action.tickets
tests: tests/test_tickets_cli.py
---
## Current behavior
action/tickets.py has `parse` but no command line. `python3 -m action.tickets` does nothing.

## Desired behavior
`python3 -m action.tickets <path>` checks one ticket file. On a valid ticket it prints `id: <id>` and one line per checklist item (item id, its marks, its text) to stdout and exits 0. On a broken ticket, a missing file, or a wrong number of arguments it prints `error: <message>` to stderr and exits 1.

## Checklist
- [C1, must] `main([path])` on a valid ticket returns 0 and prints a line with the ticket id and one line per item, each with the item id and text.
- [C2, must] `main([path])` on a ticket that breaks a rule returns 1 and prints `error:` and the rule's message to stderr, with nothing on stdout.
- [C3, must] `main([path])` on a path that does not exist returns 1 with an `error:` line and no traceback; so does a file that is not valid UTF-8.
- [C4] `main` with no path, or two paths, returns 1 with an `error:` line.
- [C5, must, keeps behavior] `parse` and the other names in action/tickets.py behave as before, and importing the module prints nothing.
- [C6] Running `python3 -m action.tickets <path>` as a process gives the same exit status and output as `main`.

## Out of scope
Changes to the ticket rules, to `parse`, and to other files.
