---
id: roles-get-stuck
size: roadmap
---
## Overview
Tollgate gets a brief that names why its AI roles get stuck, and a generic fix with every role a subagent in the user's session and no separate Claude process. The lenses narrowed the cause. It is not that every failure is "try again", because routing by cause, a stop for unfixable findings, an advisor chain, a round cap of 4 and a waiting step already exist. The cause is that these routes stop at the test lock and ignore what a role says, and that role crashes and timeouts outside the builder are not caught. The idea needs a roadmap: it covers a post-lock route, stops for hangs and loops, the end of review rounds, and runner and crash reporting. These are separate features, and a ticket plan cannot hold them in one pass. The recommended design is a few small fixes that reuse the existing park, stop, attempt_minutes and round-cap names, plus one data table for routing by cause. The brief does not add a model-based router, a new registry or a new name for an existing setting.

## Analysis
- need: ROOT CAUSE 1, no route after the lock. A retry before the lock goes to the test writer, and after the lock it only gives the builder one more try, so a wrong locked test is retried until the tries run out [driver/driver.py:604] [driver/driver.py::_decided] [docs/design.md::Special cases].
- need: ROOT CAUSE 2, role answers are not read. The builder is asked for locked_test_wrong, but no code in driver/ or gate/ reads it, and only decisions and concerns are logged [roles/builder.md:21] [driver/driver.py:459] [tests/fake_role.py:469].
- need: ROOT CAUSE 3, role failures are not caught everywhere. A RoleError or RoleTimeout in the test writer, test reviewer, advisor or brief role ends the run with a bare exit 1, and only the builder and the plan reviewer have a catch [driver/driver.py:691] [driver/driver.py:453] [driver/task.py:251].
- need: routes by cause already exist and the design extends them. A seam-only failure is not sent back, a check that names a new test file goes to the test writer, and a failed freeze goes back to the test writer at most 2 times [gate/checks.py::only_missing_seams] [driver/driver.py:378] [driver/driver.py:394].
- need: symptom 1, the long plan review, follows from findings that carry no cause. Only blocking and major findings are kept, so a minor factual error never reaches the builder, and each round can raise one new major point until the cap of 4 [driver/task.py:60] [driver/task.py:260] [driver/task.py:277]. The 7 rounds in the report do not match this cap, so the roadmap path must be checked for a path with no cap.
- need: symptom 2, the Go freeze gaps, follow from the language rules sitting in code and one table. The only language code is the compile-error table and a gotestsum rule, and the report is read only as JUnit [gate/checks.py::MISSING_NAME] [gate/junit.py:38] [gate/settings.py:89]. The fix grows the settings and hook seam, with report path and error patterns as data, and adds no parallel registry.
- need: symptom 3, the 95-minute impossible rule, follows from root cause 1 and 2. The test writer could not say the rule was wrong, and nothing read such a claim [roles/builder.md:28] [docs/design.md::Special cases].
- need: symptom 4, the hang and the repeated command, follows from limits that exist only for commands. A check has a time limit and is then retried like any failure, and the same-failure rule compares only the last two failed tries [gate/checks.py:99] [gate/checks.py:105] [driver/stop.py::same_failure].
- need: symptom 5, the unread locked_test_wrong, is root cause 1 and 2 together. A finding on a locked test file is given to a builder who may not edit it [driver/driver.py:487] [roles/builder.md:21].
- need: symptom 6, the roadmap path ignoring the runner setting, is a separate cause. make_runner already picks the runner from the setting, so the roadmap code must be found and made to use it. The Not logged in crash was not reported, which is root cause 3 [driver/session.py:292] [gate/settings.py:66] [driver/driver.py:691].
- need: what separate processes gave, and what subagents cover. Isolation was a Docker run with a mount of the copy only, no git credentials and a fresh /tmp, and the sandbox mode is marked UNTESTED [driver/roles.py:139] [driver/roles.py:146] [driver/roles.py:13]. Cost came from total_cost_usd, and session mode logs cost_usd as null, so the USD stops are off [driver/roles.py:203] [driver/stop.py:32] [driver/session.py:278]. Running with the session closed was background only, and a session run leaves a waiting step [docs/design.md::Two ways to run the roles] [driver/session.py:280].
- need: what is lost with subagents. The driver sets no time limit on a role in session mode, and only the turn cap in the agent file holds (builder 150, test writer 80, reviewer 30, advisor 15, analyst 40) [driver/session.py:263] [agents/builder.md:6]. The driver can still enforce limits on the commands it runs itself, which are the checks, and it can count turns and tries as a proxy for cost. Isolation, per-role time limits and USD cost stops are lost, and the brief must say so plainly.
- risk: a wrong-test or wrong-rule claim is untrusted input. A claim alone never waives a check or changes a lock. The advisor checks it against the check output, and the person decides what the advisor cannot.
- risk: the factual-error rule for minor findings can bring back endless rounds. The reviewer must set a factual flag with a cited line or source, and such findings stay inside the round cap [driver/task.py:260].
- risk: new routes change run/step.json, the store log and the settings, and saved answers are keyed by a hash of role, lens and inputs, so a changed input can invalidate them [driver/session.py::key] [driver/session.py:280]. New settings default to today's behavior and can be switched off.
- risk: a person's question is read on the next start, and with no answer the driver logs still_waiting and parks with no wait time [driver/driver.py:649] [driver/advisor.py:70]. Every design therefore parks and resumes from saved state as its default, and the person must confirm it.

## Goals
- A claim of locked_test_wrong, or a failure that names a locked test, is read by the driver and goes to the advisor, and then to the test writer for a replacement lock or to the person, instead of another builder try. A claim never waives a check on its own.
- Every role call is caught the same way: a RoleError or RoleTimeout in any role ends in a Stop or Parked report, with the cause, the role or check involved, and the next action for the person, and never a bare exit 1. A Not logged in crash is named.
- The roadmap path builds its runner with make_runner and so honors the runner setting, and the cause of the 7 review rounds is found and capped.
- Hang and loop stops extend the existing names: a time limit on each command the driver runs, the same-failure check across more than the last two tries, and the existing stop and park exits with a clear report. The brief says which limits a subagent cannot get.
- Review rounds end at the existing cap, open findings go to the person, and a minor finding that the reviewer flags as a factual error with a cited source still goes to the builder.
- Adding a language, test runner or report shape needs only a settings entry or one row of a data table, with no new code. The brief lists the steps and what differs from today.
- The brief lists what separate processes gave and how subagents cover each, and says plainly what is lost.

## Non-goals
- A separate Claude process, `claude -p` or any other, for any role, in any mode.
- A model-based router that classifies every failure, or a new registry or plug-in API next to the settings seam.
- A report format other than JUnit, unless a later brief asks for it.
- New names for park, stop, attempt_minutes, check_minutes or the round cap.
- A fix written for one project, one language or the Go case alone.
- Per-role USD cost stops in session mode, which cannot be enforced.

## Alternatives weighed
- Split the idea in two, with the post-lock route and crash reporting first and the stops and review end later: dropped because a roadmap already slices the work into tickets, and a second brief would repeat this analysis.
- A typed hand-off where every role answer carries an owner field and the driver routes by it: dropped because it trusts the role's own claim of the owner, and it adds a field to every role file and test fake. The kept design reads only locked_test_wrong and a factual flag, and the advisor checks them.
- The advisor as a router that classifies every Stop or repeat failure: dropped because it adds model cost and a variable result, the advisor is capped at 2 AI decisions per ticket [driver/driver.py:52], and a wrong rule still needs the person.
- Small fixes only, with no routing table: dropped because the next new kind of failure would need a new patch. The kept design adds one data table of failure cause to owner, so a new cause is a row.

## Open questions
- When Tollgate stops and hands a problem to the person, such as open review findings after the round cap, a test claimed wrong, or the same failure twice, how does it reach them in the session, and how long may a run wait for an answer before it must give up or carry on with a default?
- When the user's session closes, or its context fills, partway through a long roadmap run, what must happen to the unfinished run: resume from saved state in a later session, carry on some other way, or is it acceptable to lose it and start again?
- Who marks a minor finding as a factual error, and may the advisor overrule that flag?
- Should the new routes ship switched on by default, or switched off until the person turns them on?
- Is it acceptable to lose container isolation and USD cost stops in session mode, with a count of turns and tries as the only cost proxy?
