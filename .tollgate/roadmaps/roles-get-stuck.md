---
id: roles-get-stuck
checklist: roles-get-stuck-done
---
## Request
Find why Tollgate lets its AI roles get stuck, and fix the cause for any project, language and tool set. Every role always runs as a subagent in the user's own session: never `claude -p` or any other separate Claude process, in a task, a roadmap or a brainstorm. The cause, from the brief `roles-get-stuck`: the routes by cause that exist stop at the test lock and ignore what a role says; `locked_test_wrong` is read by no code; a RoleError or RoleTimeout outside the builder ends the run with a bare exit 1; the roadmap path ignores the `runner` setting; hang and loop stops cover only commands and only the last two tries; a minor finding that is a factual error never reaches the builder. Use the existing names park, stop, attempt_minutes, check_minutes and the round cap. Say plainly what subagents lose: container isolation, per-role time limits and USD cost stops.

## Base

## Skeleton
- roles-stuck-stop-report: Every stop or park writes one report with the cause, the role or check involved, and the next action for the person. A RoleError or RoleTimeout in any role, a Not logged in crash included, ends in that report and never in a bare exit 1.
- roles-stuck-roadmap-runner: The roadmap path builds its runner with make_runner and so honors the runner setting. Find the path that gave 7 plan review rounds when the cap is 4, and cap it.

## Features
- roles-stuck-wrong-test: The driver reads locked_test_wrong, and a check finding on a locked test file. It sends the claim to the advisor, who checks it against the check output, then to the test writer for a replacement lock or to the person. A claim never waives a check by itself.
- roles-stuck-loop-stops: Every command the driver runs has a time limit from the existing settings, and the same-failure check looks at more than the last two failed tries. A hang or a loop ends in a stop report and not in a retry.
- roles-stuck-review-end: Review rounds end at the existing cap and the open findings go to the person. A minor finding that the reviewer flags as a factual error, with a cited line or source, goes to the builder inside the cap.
- roles-stuck-language-data: Adding a language, test runner or report shape needs only a settings entry or one row of a data table, with no new code. The report path and the compile-error patterns come from that data.
- roles-stuck-session-docs: The design doc lists what separate processes gave (isolation, cost tracking, running with the session closed) and how subagents cover each one, and says plainly what is lost.

## Not yet specified
How a hand-off reaches the person and how long a run waits; what happens to a run when the session closes; who marks a factual error; default on or off for the new routes; whether to accept losing isolation and USD cost stops.
