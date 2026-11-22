---
name: analyze
description: Read this project and report how it is built, before any change is planned - its structure, entry points, frameworks, similar features, tests, and standards, each finding confirmed with a citation to the code or marked assumed. It changes no file. Use when the user runs /tollgate:analyze or asks how the project works before a change.
---

# Analyze the project

You read the project and report what you find. You change no file and run no command that changes anything. The driver runs the same analysis before it plans each task.

`TG` is the plugin root: two folders above this skill's base directory.

1. Take the request from the user's message, if there is one: the analysis then looks for how the code already does something like it. Done when you know the request, or that there is none.
2. Read `$TG/roles/analyst.md` and follow its steps as the analyst, with `task_id` set to `manual` and `commit` set to the output of `git rev-parse HEAD`. Read with Read, Grep, and Glob only. Done when the analysis has all six sections.
3. Check each citation: run `PYTHONPATH="$TG" python3 -m gate.analysis --root .` and pass the analysis on standard input. It prints the analysis with each citation it could not find made an assumption. If it says the analysis cannot be read, fix what it names and run it again. Done when it prints the analysis.
4. Show the user the printed analysis, then one line with the number of confirmed and assumed findings.

Do not write the analysis to a file, and do not plan or change anything. To build the change, the user runs `/tollgate:task`.
