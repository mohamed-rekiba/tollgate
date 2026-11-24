---
name: docs
description: Write or update a README, a document, a reference or operations doc, a doc set with diagrams, code comments, or a commit message in plain words, by the project's writing rules, and install the writing check. Use whenever you write words for people in a project, or when the user asks for docs, a README, or plain writing.
---

# Write for people

`TG` is the plugin root: two folders above this skill's base directory. The writing rules are in `$TG/lenses/review.md`, under "Writing". They ask you to write like a plain-spoken senior engineer, in the spirit of Simplified Technical English (ASD-STE100), with only the rules listed there. The reviewer reads the same file, so follow it as written.

## Before you write

1. Read the rules in `$TG/lenses/review.md`. Done when you can name the four questions a README answers.
2. Read the project's word list, `CONTEXT.md`. If there is none, ask for the scope first (see "No scope given"), then write one: each term in bold, a one-line meaning, then `_Avoid_:` and the words a reader might use instead. Start with the words of this task. Done when every term you will use has an entry.

## No scope given

When the request names a scope, write that scope in full. When it names none:

1. List what the project has and what it lacks from this set: README, word list (`CONTEXT.md`), architecture, API or interface reference, configuration reference, operations (health, runbooks), and diagrams.
2. Ask the person which to write. Do not pick the smallest set yourself.

Done when the person has named the documents.

## Write

- **README:** answer the four questions in the first screen. Put the rest under them. A README that only names the project is a stub: replace it, with the four answers first.
- **A document:** one topic for each section, and the answer first in each.
- **A diagram:** see "When a document needs a diagram". The writing check fails a Mermaid block that a change adds.
- **A design:** describe the target as it will be. The rule to say plainly what is unfinished, untested, or unverified is for a change, a report, or a review, not for a doc of the design.
- **A code comment:** say why the code is this way. Leave out what the code already says.
- **A commit message:** a subject in the form `type(scope): subject`, then a body that says why. The author is the owner of the repository. No line credits an AI.
- **A change for review:** what changes and why, then how it was checked. Say plainly what is not tested.

Done when each changed line follows the rules and uses the word list.

Last, report what you wrote, what you did not write, and what you did not check.

## When a document needs a diagram

A document that describes one of these things gets a diagram from the `diagram` skill. Draw one idea for each picture:

- The parts of a system and who uses it: a C4 context or container diagram. For the big picture in a README, add `"style": "isometric"`.
- One request or scenario between parts: a sequence diagram.
- The states of a thing with a lifecycle: a state machine.
- Stored data: an ER diagram.
- A process with choices: a flow.

Put each spec in `src` of the diagram folder: the folder of the project's existing diagram specs, or `docs/diagrams` when there is none. Build them with the command in the `diagram` skill. Place each picture in the markdown with the picture markup from that skill. Run `python3 -m diagram build <folder> --check` and make it end with 0.

A document that describes one of these things and has no diagram is unfinished. Draw the diagram, or say in the final message why there is none.

## The writing check

The check runs in two places: pre-commit runs it on each commit, on the lines the commit adds, and the gate runs it on the whole branch against main. It reads documents for the word list, long dashes, and filler, and the comments in source files for long dashes and filler. It also fails a doc that points at a file or a name the change removes: a link, a path in backticks, or `path::name`. Update the doc in the same change.

When `.tollgate/checks/check_writing.py` is missing, run `/tollgate:init`: it installs the check with the other checks. To check a branch by hand, run `python3 .tollgate/checks/check_writing.py` from the project's root and fix what it finds. Done when it ends with 0.
