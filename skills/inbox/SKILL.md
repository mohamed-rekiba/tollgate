---
name: inbox
description: List every Tollgate question that waits for a person, across all projects of a home or the current project. Use when the user runs /tollgate:inbox or asks what waits for them.
---

# Show the inbox

`TG` is the plugin root: two folders above this skill's base directory.

1. In a home, run `PYTHONPATH="$TG" python3 -m setup.inbox`. In a single project, run it with `--repo owner/name`, taking the name from `git remote get-url origin`.
2. Show each line: the project, the issue, and its title.
3. Tell the user how to answer: a comment on the issue whose first line is `tollgate decide <decision>`, from a user named under `approvers`. The issue lists the decisions it accepts.

This skill only reads. Do not answer a question for the user.
