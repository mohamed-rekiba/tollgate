---
task: base-env-up-down
commit: f96a6d382971f42b270699576d6661e4c9324d66
---
## Structure
- confirmed: the project has top folders driver/, gate/, setup/, tests/, roles/, lenses/, hooks/ [./]
- confirmed: setup/ holds standalone scripts, each with a __main__ guard, and the base suite lives there [setup/base_suite.py:1]
- confirmed: the base suite runs five commands from the settings key base: checks_run, parallel_tests, env_up_down, bad_setting_stops, one_log_line [setup/base_suite.py::NAMES]
- confirmed: the suite runs each command with shell=True, cwd=workdir, a timeout, and project_env(); a command passes only when it ends with 0, and a failure shows the last 300 characters of stderr or stdout [setup/base_suite.py:35]
- confirmed: this project's settings already set env_up_down to `python3 setup/base_env.py` [.tollgate/settings.json:58]
- confirmed: the default for base.env_up_down is an empty string, which the suite reports as not set [gate/settings.py:85]
- confirmed: state paths come from state.path(project, kind, *parts); the root comes from TOLLGATE_STATE and the key folder from TOLLGATE_KEYS [gate/state.py::_root]
- confirmed: builders is one of the allowed state kinds [gate/state.py::KINDS]
## Entry points
- confirmed: the task driver builds its copy with roles.make_copy(project, f"task-{id}") [driver/task.py:543]
- confirmed: the ticket driver calls roles.make_copy(project, ticket_id) [driver/driver.py:623]
- confirmed: make_copy clones the project with git clone --no-hardlinks into the state folder under builders/<name>, removes the remote origin, and returns the path as a string; if the copy exists it only fetches main [driver/roles.py::make_copy]
- confirmed: the driver's cleanup is roles.remove_copy(project, name), which runs shutil.rmtree with ignore_errors=True, so it never raises and a separate check must prove the path is gone [driver/roles.py::remove_copy]
- confirmed: roles.copy_path(project, name) gives the copy's path without making it [driver/roles.py::copy_path]
- confirmed: task cleanup also calls roles.remove_copy [driver/task.py:524]
- confirmed: git calls use SAFE flags and safe_env() from gate.gitio [gate/gitio.py:9]
- confirmed: the driver has no worktree creation function; worktrees appear only in setup/sync_rules.py [setup/sync_rules.py:32]
- confirmed: the temp repo needs a commit on branch main for make_copy; the existing test does git init -b main plus commit --allow-empty with -c user.name and user.email [tests/test_roles.py:132]
- confirmed: a script in setup/ run as python3 setup/x.py must put the repo root on sys.path before it imports driver or gate, as setup/agents.py does [setup/agents.py:16]
## Frameworks
- confirmed: setup scripts use only the standard library (argparse, subprocess, tempfile, shutil, pathlib) [setup/sync_rules.py:13]
- confirmed: driver/roles.py imports gate.state and gate.gitio [driver/roles.py:32]
- confirmed: ruff with line-length 100 [pyproject.toml:10]
- confirmed: the project's lint and test commands run ruff and pytest -n auto through uv [.tollgate/settings.json:55]
## Similar features
- confirmed: the closest example is CopyTest, which makes a temp git repo, calls roles.make_copy, checks the path and that there is no remote, calls roles.remove_copy, and checks the path is gone [tests/test_roles.py:130]
- confirmed: StateEnv sets TOLLGATE_STATE and TOLLGATE_KEYS to temp folders with mock.patch.dict so the copy lands in a throwaway state folder [tests/test_roles.py:17]
- confirmed: sync_one builds a temp worktree and removes it in a finally block [setup/sync_rules.py:29]
- confirmed: setup scripts use main(argv) returning an int, with errors printed to stderr [setup/sync_rules.py:61]
- assumed: setup/base_log_line.py, named in the settings, does not exist yet
## Tests
- confirmed: tests use unittest classes, run by pytest, in tests/test_*.py [tests/test_roles.py:1]
- confirmed: tests for setup scripts live in tests/test_setup.py [tests/test_setup.py:1]
- confirmed: no test file for the base suite exists yet [tests/]
## Standards
- confirmed: CLAUDE.md sets diagram rules (the diagram skill, no Mermaid) [CLAUDE.md:3]
- confirmed: the project has a contributing guide [CONTRIBUTING.md:1]
- confirmed: ruff config lives in pyproject.toml [pyproject.toml:8]
- confirmed: a pre-commit config exists [.pre-commit-config.yaml:1]
- confirmed: the project has no spec folder [./]
- assumed: commits follow type(scope): subject, as the git log shows
