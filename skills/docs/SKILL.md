---
name: docs
description: Write or update a README, a document, code comments, or a commit message in plain words, by the project's writing rules, and install the writing check. Use whenever you write words for people in a project, or when the user asks for docs, a README, or plain writing.
---

# Write for people

`TG` is the plugin root: two folders above this skill's base directory. The writing rules are in `$TG/lenses/review.md`, under "Writing". They ask you to write like a plain-spoken senior engineer, in the spirit of Simplified Technical English (ASD-STE100), with only the rules listed there. The reviewer reads the same file, so follow it as written.

## Before you write

1. Read the rules in `$TG/lenses/review.md`. Done when you can name the four questions a README answers.
2. Read the project's word list, `CONTEXT.md`. If there is none, write one: each term in bold, a one-line meaning, then `_Avoid_:` and the words a reader might use instead. Start with the words of this task. Done when every term you will use has an entry.

## Write

- **README:** answer the four questions in the first screen. Put the rest under them.
- **A document:** one topic for each section, and the answer first in each.
- **A diagram:** use the `diagram` skill. Never a Mermaid block or a picture of text.
- **A code comment:** say why the code is this way. Leave out what the code already says.
- **A commit message:** a subject in the form `type(scope): subject`, then a body that says why. The author is the owner of the repository. No line credits an AI.
- **A change for review:** what changes and why, then how it was checked. Say plainly what is not tested.

Done when each changed line follows the rules and uses the word list.

## The writing check

The check runs in two places: pre-commit runs it on each commit, on the lines the commit adds, and the gate runs it on the whole branch against main. It reads documents for the word list, long dashes, and filler, and the comments in source files for long dashes and filler.

When `.tollgate/checks/check_writing.py` is missing, run `/tollgate:init`: it installs the check with the other checks. To check a branch by hand, run `python3 .tollgate/checks/check_writing.py` from the project's root and fix what it finds. Done when it ends with 0.
