---
id: report-minutes
plan: ticket-minutes
seams: report.ticket_row, report.status, report.render
tests: tests/test_report_minutes.py
---
## Current behavior
The status table and the task report show state, tier, attempts, score, and cost for each ticket, but not how long the ticket took. Only the task report has one overall "Time:" line.

## Desired behavior
Each ticket row has the minutes from the first to the last event in that ticket's log, rounded to a whole number. The status table and the task report each show it in a Minutes column placed right after Cost USD, before Pull request, in both tables.

## Checklist
- [C1, must] ticket_row(events) returns "minutes": the time from the first to the last "at" stamp in those events, rounded to a whole number (90 seconds gives 2; 29 seconds gives 0).
- [C2, must] status() has a Minutes column (right after Cost USD) in its header and separator, and each ticket row shows that ticket's minutes.
- [C3, must] render() has a Minutes column (right after Cost USD) in its ticket table, and each row shows that ticket's own minutes, not the task's.
- [C4] A ticket whose log has one event, or no "at" stamps, shows 0.
- [C5, must, keeps behavior] The "Time:" line of the task report and the other columns are unchanged, in the same order; only Minutes is inserted, right after Cost USD.

## Out of scope
The task's plan log, the brief, and the Time line.
