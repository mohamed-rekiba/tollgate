# S2: the freeze and the gate on GitHub

Question: do the freeze and gate workflows work on GitHub, pass an honest build, and fail each kind of cheat?

Run: 2026-11-21, on this repository, after pull request #10 set Tollgate up here without rulesets. The lab tickets live only on branches `tg/lab-<n>`. Their freeze tags stay. The pull requests were closed, not merged. Script: `tests/proof_gate_github.py`.

## The freeze

Run 44880855545, `tollgate freeze lab-1`, on the main branch, started by hand, succeeded. It created `tg/freeze/lab-1/1` with the manifest in the tag message, and saved the same manifest as the artifact `tollgate-manifest`. The manifest marked `test_c1_shout` as new, failing before the build, and `test_c2_matches_kept` as kept behavior, passing before the build.

## The gate

| Pull request | Change | Gate | Rule that failed |
| --- | --- | --- | --- |
| #11, `tg/lab-1` | An honest build | Passed, tier 1 | |
| #13, `tg/lab-2` | The build also edits a locked test | Failed | 3 |
| #14, `tg/lab-3` | The build also adds a skip mark to a locked test | Failed | 3 |
| #15, `tg/lab-4` | The build also adds `pytest.ini` | Failed | 4 and 6: tier 4, no approval, no server review |
| #16, `tg/lab-5` | The build also changes `action/paths.py`, a tier 4 path | Failed | 4 and 6 |
| #17, `lab-no-ticket` | A branch that names no ticket | Failed | 1 |

For #11, the gate read the run of the freeze through the REST API, matched its title `tollgate freeze lab-1`, downloaded the artifact, and found the same manifest as the tag.

## Bugs it found

- The gate job fetched the change with no credentials, which fails on a private repository. Fixed in #12: that job runs only code from main, so it keeps its read-only token.
- A comment posted through this session gets a footer added to it, so `tollgate check` never matched exactly. The trigger now accepts a comment that starts with `tollgate check`. The approval comment still must match exactly.
- This session's proxy refuses a REST path that ends in a slash. The driver's tag listing no longer uses one.

## Not shown here

- A forged freeze tag pushed from a laptop. This session cannot create tags, and a forged tag through the REST API was refused as undermining oversight. Unit tests cover the rule: `tests/test_review_findings.py`.
- The rulesets. They go on last; see `docs/status.md`.
