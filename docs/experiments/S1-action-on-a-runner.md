# S1: the composite action on a runner

Question: does `action/action.yml` run Tollgate's Python on a GitHub runner, refuse an unknown command, and keep shell text in its arguments as text?

Run: branch `tg-lab/s1-action`, commit `68a36d1`, workflow `.github/workflows/lab-s1-action.yml` on that branch. Check run 136664895144 ended with success.

| Step | What it did | Result |
| --- | --- | --- |
| Normal call | `command: gate`, `args: --help` | Ran. The job went on. |
| Unknown command | `command: rm`, `args: -rf /` | Ended with code 2. The action refused it before Python started. |
| Shell text | `command: settings`, `args: $(touch /tmp/pwned) ;touch /tmp/pwned2` | Ended with code 2: the settings command read the text as two file arguments. Neither file was created. |

The last step of the job checked both files and the outcome of the unknown command. It passed, so the job passed.

What this does not show: the freeze and the gate workflows themselves. They run only from the main branch, and this session cannot start a workflow by hand. `tests/proof_stage1.py` covers them, run by the owner against a lab repository.

A note from the run: `actions/checkout@v4` targets Node.js 20, which GitHub now runs on Node.js 24 with a warning. The templates keep v4 until a newer major version is checked.
