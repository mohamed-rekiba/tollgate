"""The tests do not read the signing settings of the machine they run on.

A temporary repository in a test has no signing key, so a global commit.gpgsign=true
makes each `git commit` in it fail. Git reads these variables after the global file.
"""

import os

if "GIT_CONFIG_COUNT" not in os.environ:
    os.environ.update({"GIT_CONFIG_COUNT": "2",
                       "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false",
                       "GIT_CONFIG_KEY_1": "tag.gpgsign", "GIT_CONFIG_VALUE_1": "false"})
