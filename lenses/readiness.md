# Lens: readiness

You read the plan, the analysis of the project, and the code.

1. **Every name exists.** Each file, function, command, or address that the plan says exists today must exist. One that does not is a `blocking` finding. Give the name and where you looked.
2. **No decision is left to the builder.** A choice that changes behavior and that the plan does not make, such as an error format, a limit, or a name in a public interface, is a `major` finding.
3. **Each ticket fits one session.** A ticket that changes more than about 8 files or mixes unrelated work is a `major` finding.
4. **The order works.** A ticket that needs a later ticket's work is a `blocking` finding.
5. **The plan rests on facts.** A part of the plan that rests on an assumed fact of the analysis, and does not ask about it under Assumptions, is a `major` finding. A specified fact is not an assumption: the plan need not list it under Assumptions.
6. **Each risk has a test.** A risk under Risks that no checklist item covers is a `major` finding. Its kind of test tells you which item should cover it: an edge case is `edge` or `boundary`, a failure is `error`, and a security or speed risk is `security` or `performance`. A compatibility risk that no item or ticket answers is `major` too.

7. **The checks of the project pass.** A plan that leaves out, puts out of scope, or deletes a file that a check of the project requires, such as a README that its writing check asks for, is a `major` finding. Such a file is never out of scope.

8. **The docs move with the code.** A plan that changes behavior, a command, a setting, an interface, or the architecture, and lists no README, doc, diagram, or comment that describes it, is a `major` finding.

9. **The kinds are honest.** Each reason under `## Not covered` must be true for this change: "no concurrency" is false when the code takes a lock or runs work in parallel. A ticket that fixes a bug and has no `fixes:` line, or a `performance` or `concurrency` item whose number tests nothing that matters, is a `major` finding.

10. **The plan follows the spec.** A plan that differs from a specified fact of the analysis, and lists no change to that doc under Files, is a `major` finding. Give the fact and the part of the plan that differs.

**A fix round.** When your inputs hold `fix`, the plan is a new version of an approved plan, written to fix the problems that `fix` lists. Read the plan against those problems as well as the request: a ticket that fixes one of them is needed. The tickets of the approved plan are locked: do not ask to change, merge into, or drop them. A fix goes in a new ticket with its own test file.

Done when you have checked every name, every ticket, and every line under Risks, Assumptions, and Not covered.
