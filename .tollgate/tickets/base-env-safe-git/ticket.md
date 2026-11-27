---
id: base-env-safe-git
plan: base-env-up-down
seams: setup.base_env.git, setup.base_env.main
tests: tests/test_base_env_safe_git.py, tests/test_base_env.py
fixes: The git() helper in setup/base_env.py runs plain git with no gate.gitio SAFE options and no safe_env().
---
## Current behavior
The git() helper in setup/base_env.py runs `git` with no SAFE options and no safe_env(). A hook or a file system monitor in the temp repo or the copy could run code, and replace refs are followed. make_copy itself uses both.

## Desired behavior
Every git call in setup/base_env.py puts gate.gitio SAFE right after `git` and passes env=gate.gitio.safe_env(). The result of main() does not change.

## Checklist
- [C1, must, happy] Each git call of a run (init, commit, remote, rev-parse in the copy and in the repo) starts with git followed by the SAFE options, and has GIT_NO_REPLACE_OBJECTS=1 in its env.
- [C2, must, error] When a git call fails, main() still returns 1, prints the failed step to stderr, and removes the temp folders.
- [C3, must, regression] A test that records every subprocess.run call of setup.base_env fails now, because a call has no SAFE options and no GIT_NO_REPLACE_OBJECTS.
- [C4, must, keeps behavior, happy] main() still returns 0 when the copy is made, checked, removed, and gone: tests/test_base_env.py.
- [C5, must, keeps behavior, e2e] python3 setup/base_env.py from another cwd still ends with 0: tests/test_base_env.py.
- [C6, edge] The SAFE list and safe_env come from an import of gate.gitio, not a copy in setup/base_env.py.
- [C7, security] The recorded git calls carry the options that turn off hooks and the file system monitor, so no hook of the temp repo or the copy runs.

## Not covered
- boundary: the script takes no size or range input.
- integration: the ticket base-env-up-down already covers the real make_copy and remove_copy calls.
- performance: the change adds two options to each git call, with no speed goal.
- concurrency: the script keeps no shared state and uses its own temp folders.

## Out of scope
Any change to driver/roles.py, gate/gitio.py, or the settings.
