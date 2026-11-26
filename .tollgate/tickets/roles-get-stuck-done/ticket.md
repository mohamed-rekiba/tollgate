---
id: roles-get-stuck-done
plan: roles-get-stuck
tests: tests/test_roles_stuck_done.py
---
## Current behavior
A locked test that is wrong is retried by the builder until the tries run out. A RoleError or RoleTimeout outside the builder ends the run with exit 1 and no report. The roadmap path can start a separate process.

## Desired behavior
Every problem goes to the role that can fix it. Every stop writes a report. Every role runs as a subagent in the user's session.

## Checklist
- [C1, must, happy] A builder answer with locked_test_wrong set is read by the driver, and the claim reaches the advisor and then the test writer or the person, not another builder try.
- [C2, must, error] A RoleError or RoleTimeout in the test writer, test reviewer, advisor or brief role ends in a stop report with the cause, the role and the next action, and never a bare exit 1.
- [C3, must, regression] The roadmap path with runner set to session builds its runner with make_runner and starts no separate process.
- [C4, must, edge] The same failure on 3 failed tries in a row, with a different failure between, stops the ticket with a report.
- [C5, boundary] A plan review ends at 4 rounds, and the open findings go to the person.
- [C6, must, security] A wrong-test claim never waives a check: the check still runs and still fails until a replacement lock passes.
- [C7, must, keeps behavior] A failed freeze still goes back to the test writer at most 2 times: tests/test_driver_loop.py.
- [C8, performance] A command that runs past check_minutes of 20 is stopped within 1 minute of the limit.

## Not covered
- integration: the fakes in tests/fake_role.py stand in for the roles.
- e2e: no command or web address changes.
- concurrency: the driver runs one role step at a time.

## Out of scope
How a hand-off reaches the person, and what happens when the session closes.
