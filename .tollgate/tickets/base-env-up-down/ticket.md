---
id: base-env-up-down
plan: base-env-up-down
seams: setup.base_env.main, driver.roles.make_copy, driver.roles.remove_copy
tests: tests/test_base_env.py
---
## Current behavior
setup/base_env.py does not exist. The settings key base.env_up_down points to it, so the base suite fails that check.

## Desired behavior
python3 setup/base_env.py builds a temp git repo, makes a copy with roles.make_copy in a temp state folder, checks it, removes it with roles.remove_copy, checks it is gone, and ends with 0. On any failed step it prints a message to stderr and ends nonzero.

## Checklist
- [C1, must, happy] main() returns 0 when the copy is made, checked, removed, and gone.
- [C2, must, error] When a step fails (for example make_copy raises or the path stays after remove_copy), main() returns nonzero and prints a message naming the step to stderr.
- [C3, must, integration] The script calls the real roles.make_copy and roles.remove_copy: a test watches them with a wrapper that calls the real function, and sees one call each.
- [C4, must, e2e] Running python3 setup/base_env.py from another cwd ends with 0.
- [C5, must] After the run, the temp state folder and temp repo are removed, and the real state folder is not touched, also after a failure.
- [C6, edge] The copy has no origin remote and holds the commit of the temp repo.
- [C7, security] The script sets TOLLGATE_STATE and TOLLGATE_KEYS only for its run, and restores their old values after.

## Not covered
- regression: the ticket fixes no bug.
- boundary: the script takes no size or range input.
- performance: the script is a single run of one clone of an empty repo, with no speed goal.
- concurrency: the script keeps no shared state and uses its own temp folders.

## Out of scope
setup/base_log_line.py and the other base checks. Any change to driver/roles.py or the settings.
