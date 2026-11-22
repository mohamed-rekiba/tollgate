---
name: inbox
description: List every Tollgate question that waits for you, across all projects of a home or the current project, and record your answer. Use when the user runs /tollgate:inbox, asks what waits for them, or answers a question.
---

# Show the inbox

`TG` is the plugin root: two folders above this skill's base directory. Words: a **question** is one the driver asks when it is stuck, kept by the store in the state folder.

1. In a home, run `PYTHONPATH="$TG" python3 -m setup.inbox`. In a single project, run it with `--project .`.
2. Show each line: the project, the number of the question, its title, and its options.
3. Ask the user which option they pick for each question, and an optional hint for the role that reads it.
4. Record each answer with their words: `PYTHONPATH="$TG" python3 -m setup.inbox --project <project> answer <n> <decision> [hint]`. The decision must be one of the options.

Done when each answer prints `answered question <n>`, or the user has no answer yet.

Never pick an option for the user. Record only what they said.
