# 3.10: Tollgate against Claude Code alone

**State: run. Two measures are pending: the blind review and the fixes after merge.**

Run on 2026-11-21, on this repository. Both arms ran on GitHub Actions, in the same container (`tollgate-builder:ci`, Claude Code 2.1.330), with the same model access and the same request text (`requests.json`).

- **Tollgate arm:** `tollgate.yml`, kind `task`. The driver plans, writes and freezes the tests, builds, checks, scores, reviews, and opens a pull request.
- **Plain arm:** kind `plain`. Claude Code is given the request once and opens a pull request.

## Results

| Ticket | Tollgate, round 1 | Tollgate, round 2 | Plain |
| --- | --- | --- | --- |
| e310-01 | parked, 4 attempts, 0.90 USD | **PR #63**, 1 attempt, 0.81 USD | PR #46, 0.07 USD, style check failed |
| e310-02 | parked, 3 attempts, 0.80 USD | parked, 5 attempts, 1.08 USD | PR #47, 0.06 USD |
| e310-03 | parked, 4 attempts, 0.85 USD | **PR #61**, 1 attempt, 0.60 USD | PR #49, 0.08 USD |
| e310-04 | parked, 5 attempts, 0.73 USD | plan rejected, 0.15 USD | PR #48, cost record lost |
| e310-05 | PR #56, 1 attempt, 0.61 USD | **PR #60**, 1 attempt, 0.55 USD | PR #51, 0.08 USD |
| e310-06 | parked: the freeze refused the tests 3 times | parked: the freeze refused the tests 3 times, 0.78 USD | PR #50, 0.07 USD |
| e310-07 | parked, 4 attempts, 0.99 USD | plan rejected, 0.17 USD | PR #52, 0.07 USD |
| e310-08 | PR #58, 1 attempt, 1.17 USD | **PR #62**, 1 attempt, 0.58 USD | PR #53, 0.08 USD |
| e310-09 | PR #57, 1 attempt, 0.74 USD | **PR #64**, 1 attempt, 0.85 USD | PR #55, 0.07 USD |
| e310-10 | parked, 5 attempts, 1.21 USD | **PR #65**, 1 attempt, 0.90 USD | PR #54, 0.09 USD |
| **Reached a pull request** | **3 of 10** | **6 of 10** | **10 of 10** |
| **Passed tests and style** | 3 of 3 | 6 of 6 | 9 of 10 |
| **Invented names** | 0 | 0 | 0 |
| **Cost per ticket** | about 0.9 USD | about 0.7 USD | about 0.07 USD |
| **Time per ticket** | 2 to 3 minutes | 2 to 4 minutes | under 1 minute |

Costs are what Claude Code reports. With an OAuth token they are a measure of use, not a bill.

## What the rounds found

Round 1 found three defects in Tollgate, not in the builder:

1. **No check output.** The builder saw only "check style failed", never the check's output.
2. **Lint errors in locked tests.** Five locked test files failed the style check, and the builder may not change a locked test. So those tickets could never pass. Confirmed by running ruff on the locked files.
3. **No freeze reason.** A failed freeze reported a link, not its reason.

They were fixed in #59, and round 2 ran on that exact commit.

Round 2 found three more:

1. **Header format.** Two plans were rejected for their header. The builder had no example of the format.
2. **Log timing.** A freeze's reason was read before GitHub had published the job's log.
3. **Unrecorded rejection.** e310-06's freeze correctly refused a test that passed before the build without the "keeps behavior" mark. That reason never reached the test writer, because of the second defect.

They were fixed after the run, in #66. Per the advisor, round 2 is the last round on these tickets. Further fixes need fresh tickets.

Round 2 is post hoc: it ran on the tickets the fixes were found from. The plain arm had one try. Round 1 is the headline.

## What this says so far

- **Invented names:** none in either arm. On tickets this small, this measure does not separate the arms.
- **Reaching a merge:** the plain arm reached a pull request every time, and 9 of its 10 passed the checks. Tollgate reached 3, then 6, with every one passing.
- **Cost:** Tollgate cost about 10 times as much and took 2 to 4 times as long. It plans, writes and freezes tests, and runs up to six model reviews for each ticket.
- **The verdict waits:** the plan asks whether Tollgate gives fewer invented names and fewer fixes at an acceptable cost. That rests on the two pending measures.

## What is merged

As the advisor set before the run: odd tickets merge the Tollgate arm, even tickets merge the plain arm. e310-07 had no Tollgate pull request, so its plain arm merged.

| Ticket | Merged | Arm |
| --- | --- | --- |
| e310-01, 03, 05, 09 | #63, #61, #60, #64 | Tollgate, round 2 |
| e310-02, 04, 06, 08, 10 | #47, #48, #50, #53, #54 | plain |
| e310-07 | #52 | plain, since Tollgate did not reach a pull request |

## Pending, for the owner

1. **Blind review.** `packet/` holds each of the six tickets that have both arms, as `A` and `B`. Spend 15 minutes on each diff and mark it "merge" or "not merge". Only then open `key-do-not-open-before-review.json`, which says which arm is which.
2. **Fixes after merge,** due on 2026-12-05, 14 days after the merges. For each merge commit, run:

   ```
   python3 docs/experiments/e310/fixes_after_merge.py --repo . --merge <commit>
   ```

## Files

- `requests.json`: the ten requests.
- `pairs.json`: the head commit of each arm.
- `packet/` and the key: the blind review.
- `invented_names.py`, `fixes_after_merge.py`, `blind_packet.py`: the measuring scripts.
- The raw logs are on the branch `tollgate-logs`. `python3 -m driver.report --project . --logs-branch tollgate-logs` reads them.

## Cleanup on 2026-11-21: not a fix

The 3.10 requests asked for command-line entry points and flags (tickets-cli, plan-cli, roadmap-check-cli, ticket-file-cli, human-flag, inbox-json-flag, and the plain arm's e310-02, -04, -06, -07, -08, -10). The plan's decision is "skills in Claude Code, and no command-line program", so those requests should not have been chosen. Every one that merged was removed on 2026-11-21, in both arms. The fixes-after-merge count must not count these removals: the changes did what they were asked; the request was wrong. Only report-minutes stays, because `/tollgate:status` shows its column.
