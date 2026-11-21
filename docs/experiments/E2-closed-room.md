# E2: The closed room

**Result: passed, both halves.**

## The model half, on GitHub

Run `tollgate e2 room-1`, on 2026-11-21, as `tollgate.yml` kind `e2`: Claude Code 2.1.330 in `tollgate-builder:ci`, with only `CLAUDE_CODE_OAUTH_TOKEN` passed in.

| Check | Result |
| --- | --- |
| The output parses as data and holds a cost | Yes, 0.04 USD. |
| The file changed in the copy | Yes. |
| A push from inside, to GitHub, fails | Yes. |
| GitHub tokens inside the container | 0. |

## The container half

## What ran

`tests/proof_container.py`, on 2026-11-21, with Docker 29.10 and a local image (`tollgate-lab/py:local`). The image holds only Python 3.13, git with its HTTPS helper, a shell, and CA certificates. It was built from the workspace's own files, because the workspace cannot reach Docker Hub.

The roles were fake roles with the same contract as Claude Code: read the prompt on standard input, print `{"result": ..., "total_cost_usd": ...}`.

| Check | Result |
| --- | --- |
| A role in the container writes to the copy, and the driver reads its answer and cost. | Passed. |
| A push from inside, to the local server, fails. | Passed: the server's path is not in the container. |
| A push from inside, to `https://github.com/tollgate-ai/tollgate.git`, fails. | Passed. The container reached GitHub, which asked for a user name: no credentials are inside. |
| A `GH_TOKEN` set for the driver does not reach the role. | Passed: the role saw no variable with `TOKEN` or `GH` in its name, and an empty home folder. |
| Files written inside belong to the user who runs the driver. | Passed. |
| The driver builds a ticket with `sandbox: container`, every role in the container: one failed attempt, one passed attempt, a pull request. | Passed. |

## How to run it again

```
TOLLGATE_TEST_IMAGE=<image with python3 and git> python3 -m unittest tests.proof_container -v
```

Without `TOLLGATE_TEST_IMAGE` or a container daemon, the tests skip. CI has neither, so CI skips them.
