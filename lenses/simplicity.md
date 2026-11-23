# Lens: simplicity

You read a whole plan and the analysis of the project. For each part of the plan, ask four questions:

1. **Is it needed?** It serves something the task asks for. A part that serves a need nobody stated is a `major` finding.
2. **Does the code already have it?** Search the project. A part that rebuilds something the project has is a `major` finding. Name the file that has it.
3. **Is anything built for later?** Extension points, options, or layers with one user today are a `minor` finding, or `major` if they add a ticket.
4. **Does it fit the architecture the analysis found?** A part that solves something in a new way, when the request does not ask for a new architecture, is a `major` finding. Name the part of the analysis it breaks from.

The plan's Reuse section must name what the code already has. A thing the analysis found that the plan rebuilds instead of reusing is a `major` finding.
A `keeps behavior` item that asks for a new test when an existing test already asserts the behavior is a `major` finding: name the test as `file::test`, and point the item at it.
A plan that could drop a whole ticket and still do the task gets a `blocking` finding.

**A fix round.** When your inputs hold `fix`, the plan is a new version of an approved plan, written to fix the problems that `fix` lists. Read the plan against those problems as well as the request: a ticket that fixes one of them is needed. The tickets of the approved plan are locked: do not ask to change, merge into, or drop them. A fix goes in a new ticket with its own test file.

Done when every ticket and every file in the plan has been asked all four questions.
