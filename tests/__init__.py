"""The tests do not read the git settings of the machine, or of the hook, that runs them.

Signing: a temporary repository in a test has no signing key, so a global
commit.gpgsign=true makes each `git commit` in it fail. Git reads these variables
after the global file.

Location: git sets GIT_DIR and its relatives for a hook that runs from a linked
worktree. A test that runs `git init` or `git commit` in a temporary folder would then
act on the repository that runs the hook. The tests start with these variables unset.
"""

import os

if "GIT_CONFIG_COUNT" not in os.environ:
    os.environ.update({"GIT_CONFIG_COUNT": "2",
                       "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
                       "GIT_CONFIG_KEY_1": "tag.gpgsign", "GIT_CONFIG_VALUE_1": "false"})

# The same goes for what pre-commit sets for a hook. A test that commits in a temporary repository
# with Tollgate's hooks would otherwise take its git step from the hook that runs the tests.
for _name in [k for k in os.environ if k.startswith("PRE_COMMIT_")
              and k not in ("PRE_COMMIT_HOME", "PRE_COMMIT_NO_CONCURRENCY")]:
    os.environ.pop(_name, None)

for _name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_PREFIX",
              "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE"):
    os.environ.pop(_name, None)
