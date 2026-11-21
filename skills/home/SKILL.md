---
name: home
description: Create or manage a Tollgate home - one private repository that holds many projects as git submodules and the rules they share. Use when the user runs /tollgate:home, /tollgate:home add owner/name, or /tollgate:home sync.
---

# Manage a home

`TG` is the plugin root: two folders above this skill's base directory. Run every script as `PYTHONPATH="$TG" python3 -m <module>` from the home folder.

Words: a **home** is a private repository with a list of projects. Each project is a git submodule: a link from the home to the project's own repository.

## `/tollgate:home`: create one

1. Confirm the current folder is empty, apart from `.git`. If not, stop and say so.
2. Ask the user for the GitHub repository of the home, as `owner/name`, if they want one. It must already exist and be private.
3. Run `python3 -m setup.home init` with `--remote owner/name` if they gave one. It refuses a public repository.
4. If there is a remote, push: `git push -u origin main`.

Done when `home.json` exists.

## `/tollgate:home add owner/name`

1. Run `python3 -m setup.home add owner/name`. It adds the project under `projects/<name>` and prints whether the project has Tollgate settings.
2. If `has_settings` is false, offer to run `/tollgate:init` inside `projects/<name>`.
3. Push the home.

Done when `python3 -m setup.home list` shows the project.

## `/tollgate:home sync`

1. Show the user the files in `rules/lenses/`. These are the shared rules.
2. Run `python3 -m setup.sync_rules`. It opens one pull request in each project.
3. List the pull requests. A person reviews and merges each one. Nothing merges on its own.

The home never weakens a project. Each project keeps its own settings, and GitHub reads them from the project.
