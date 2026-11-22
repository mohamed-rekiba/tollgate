---
name: home
description: Create or manage a Tollgate home: one git repository on this machine that holds many projects as git submodules, and the rules they share. Use when the user runs /tollgate:home, /tollgate:home add, or /tollgate:home sync.
---

# Manage a home

`TG` is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -m <module>` from the home folder.

Words: a **home** is a git repository with a list of projects. Each project is a git submodule: a link from the home to the project's own repository. The **shared rules** are the lens files in the home's `rules/lenses/`.

## `/tollgate:home`: create one

1. Confirm the current folder is empty, apart from `.git`. If not, stop and say so.
2. Run `python3 -m setup.home init`.

Done when `home.json` exists.

## `/tollgate:home add <project>`

1. Run `python3 -m setup.home add <project>`, where the project is a folder or a git address. It adds the project under `projects/<name>` and prints whether the project has Tollgate settings.
2. If `has_settings` is false, offer to run `/tollgate:init` inside `projects/<name>`.

Done when `python3 -m setup.home list` shows the project.

## `/tollgate:home sync`

1. Show the user the files in `rules/lenses/`.
2. Run `python3 -m setup.sync_rules`. In each project, it puts the shared rules in `.tollgate/lenses/` on the local branch `tollgate-sync`. It prints one line for each project.
3. Show each line. Tell the user to approve and merge the branch `tollgate-sync` with `/tollgate:merge tollgate-sync` in that project. Nothing merges on its own.

A sync branch is a change made by hand, with no pass record, so `setup.merge list` does not show it. The owner signs an approval of it, then merges it.

The home never weakens a project. Each project keeps its own settings, and the gate reads them from the project's main branch.
