---
id: base-env-up-down
tickets: base-env-up-down, base-env-safe-git
---
## Task
Add setup/base_env.py. It builds a throwaway test environment the way the driver builds one for a task (a temp git repo plus the driver's own copy or worktree creation function), checks it exists and works, tears it down with the driver's own cleanup function, and checks it is gone. It ends with 0 only when every step held, and nonzero with a message on any failure. It must call the real driver functions and must not fake them.

## Design
No spec docs exist, so the design follows the analysis. setup/base_env.py is a standalone script with a main(argv) -> int and a __main__ guard, like setup/sync_rules.py. It puts the repo root on sys.path (as setup/agents.py does), then imports driver.roles. The driver has no worktree function, so it uses roles.make_copy. Steps: set TOLLGATE_STATE and TOLLGATE_KEYS to temp folders (restored after), make a temp git repo on main with one commit (git init -b main, commit --allow-empty with -c user.name and user.email, using gate.gitio SAFE, a list of git options that turn off hooks and fsmonitor, and safe_env, a function that returns the environment with GIT_NO_REPLACE_OBJECTS=1), call roles.make_copy, check the path exists, is a git repo, has no origin remote, and has the commit. Then call roles.remove_copy and check the path is gone, because remove_copy ignores errors. Each step prints a short line; any failed step prints a message to stderr and returns 1. The temp folders are always removed in a finally block. The script is already named in .tollgate/settings.json as base.env_up_down, so no settings change is needed. No behavior of existing code changes, and the repo has no doc that describes the base suite.

## Files
create setup/base_env.py
create tests/test_base_env.py
modify setup/base_env.py
create tests/test_base_env_safe_git.py

## Seams
setup.base_env.main
driver.roles.make_copy
driver.roles.remove_copy

## Reuse
driver/roles.py: make_copy, remove_copy, copy_path, unchanged.
gate/gitio.py: SAFE flags and safe_env, unchanged.
gate/state.py: path, unchanged (read through the env vars).

## Risks
- remove_copy never raises, so the script must check the path is gone itself.
- The real state folder must not be touched: the env vars point to temp folders and are restored.
- Git needs user.name and user.email: pass them with -c so no global config is needed.
- A failing step must still clean the temp folders.
- Run as python3 setup/base_env.py from any cwd: the repo root goes on sys.path first.

## Assumptions
none

## Tickets
- base-env-up-down: write setup/base_env.py, which builds, checks, tears down, and checks a real driver copy.
- base-env-safe-git: run every git call of setup/base_env.py with gate.gitio SAFE and safe_env().
