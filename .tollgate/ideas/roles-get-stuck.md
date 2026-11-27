Find the root cause of why Tollgate let its AI roles get stuck, and design a generic fix.

## Goal
Tollgate exists to help AI agents reach the best result: correct code, correct tests, and a decision made when one is needed. Locking tests and scoring tries are means to that end, not the goal. Find the root cause of the failures below. Do not list their symptoms. Then propose a design that fixes the cause for any project, in any language, with any tools, and not only for the case below.

## What happened (one real run, in a Go project; use it as evidence, not as the scope)
1. Plan review ran 7 rounds, with 3 reviewers each, about 2.5 hours, for one small story. Each round found one new "major" point, mostly about doc wording. Minor findings never reached the builder. A real mistake, a key order that Postgres jsonb does not keep, was flagged as minor in round 4 and was still built into the tests later.
2. The freeze could not lock Go tests at all:
   - It ran vet and lint on new tests that call a function that does not exist yet, and refused them.
   - It matched report entries to files by Python rules.
   - It did not read gotestsum's report shape.
   Each gap showed up only on a real run, one at a time.
3. A test writer spent about 95 minutes trying to satisfy an impossible rule. It built a probe program at test time, a workaround, because nothing told it the real problem or let it say "this rule is wrong here".
4. A lint run hung for 47 minutes, and a test file hung on every run. No step watched for a hung process or a loop, and the same failing command ran again and again.
5. A check failed on a locked test file. The driver gave the finding to the builder, who may not edit locked tests, so every try would fail the same way. The builder reported `locked_test_wrong`, and no code reads that field. Nobody was asked to fix the test.
6. The roadmap path started each role as its own process with `claude -p`, in Docker, although the project chose session mode. That breaks the rule that roles run as subagents of the user's own session. The run crashed at once with "Not logged in", and the crash was not reported.

## Questions to answer
- What single design flaw, or few flaws, explain all of these? For example:
  - Does Tollgate treat any failure as "try again" when it should ask "who can fix this, and what is the real issue"?
  - Does it send a finding to a role that cannot act on it?
  - Does it lack a step that checks with the advisor when the same problem repeats, or when a rule looks wrong for this project?
- How should Tollgate route a problem to the role that can fix it: the builder for code, the test writer for a test, the planner for a plan, the advisor or the person for a rule or a decision?
- How should a role report "the rule or the test is wrong", and what happens next? Who checks the claim?
- How should Tollgate stop a long run, a hang, or a loop?
  - Time limits for each command and each role.
  - Detecting the same failure twice.
  - Giving up with a clear report and not retrying.
- How should review rounds end? For example: a cap on rounds, then the open findings go to the person, and a minor finding that is a factual error still goes to the builder.
- How should Tollgate handle any project's language, test runner, report format and checks without code written for each one? Example: Go with gotestsum and golangci-lint, so it does not fail one output shape at a time.
- With every role running as a subagent in the same session, what replaces what the separate processes gave? List each thing they gave, such as isolation, cost tracking and the ability to run while the session is closed, and say how the design covers it, or say plainly what is lost.

## Rules for the brainstorm
- Every solution must be generic. It must work for any project, language and tool set. Never write a fix for this project or this one case. If a part must know a language or tool, design it as a general mechanism that any language or tool can plug into, and say how a new one is added.
- Never use `claude -p` or any other separate Claude process for a role. Every role (analyst, planner, builder, test writer, reviewer, advisor) always runs as a subagent in the user's current session, for a single task, a roadmap and a brainstorm alike. A design that needs a separate process is out of scope.
- Read the Tollgate source and docs (driver/, gate/, roles/, docs/design.md) to check each claim. Cite file and line.
- Separate the root cause from its symptoms. Say why each symptom follows from the cause.
- Propose at most 3 designs. Recommend one, with its cost and what it does not solve.
- Keep the brief short enough to plan from.
