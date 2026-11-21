# Lab cleanup

Done on 2026-11-21: the branches and tags below are gone from GitHub. The list stays as a record.

The experiments and proofs ran in this repository, because this session could not create a separate lab repository. This session could not delete branches or tags either. You delete these.

## Branches

Merged work branches, safe to delete:

```
git push origin --delete chore/pin fix/gate-fetch fix/github-findings fix/prove-gate s3/plan-review s3/task-loop s4/scale tg/e2-container tg/handover tg/s1-core tg/s1-freeze tg/s1-hardening tg/s1-setup tg/s2-driver tollgate-setup docs/final
```

Lab branches of the experiments and the gate proofs. Their pull requests are closed:

```
git push origin --delete tg-lab/ci-red tg-lab/e1-run tg-lab/e3-pr tg-lab/e5-action tg-lab/s1-action tg/lab-1 tg/lab-2 tg/lab-3 tg/lab-4 tg/lab-5 tg/lab-6 lab-no-ticket tg/proof-20261121 tg-plan/lab-plan
```

## Tags

- `tg-lab/e1-44843991100`: `git push origin --delete refs/tags/tg-lab/e1-44843991100`
- `tg/freeze/lab-1/1` to `tg/freeze/lab-5/1`, `tg/freeze/proof-20261121/1`, and `tg/plan/lab-plan/1`. The tag ruleset keeps them. To delete them, first turn the ruleset `tollgate tags` off in the repository settings, delete the tags, then turn it on again.
