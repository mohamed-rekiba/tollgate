# E3, the part that needs a ruleset

1. Apply the ruleset that requires the `tollgate gate` check on `main`.
2. Open a pull request that breaks a locked test and also adds `.github/workflows/fake.yml` with one job named `tollgate gate` that always passes.
3. Record whether GitHub allows the merge.

If it allows the merge, the gate needs a check name that a change cannot copy, or a second required check. Record the result in E3-clean-server-job.md.
