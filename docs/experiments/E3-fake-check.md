# E3: a fake gate check from a workflow added on a branch

**Result: the risk is real. Whether a required check would accept the fake needs the rulesets on.**

Run on 2026-11-21. The branch `tg-lab/e3-fake` added `.github/workflows/lab-e3-fake.yml`, which runs on push from the branch's own copy. With only the permission to post checks, it posted a passing check named `tollgate gate` on its own commit. Pull request #45 was then opened and closed, never merged.

| Observation | Result |
| --- | --- |
| The fake check was created | Yes, by the same app as the real gate, `github-actions`. |
| Two checks named `tollgate gate` on one commit | Yes: the fake success, and the real gate's failure. |
| Which one GitHub shows | The newest. The real gate ran after the fake, so it showed the failure. After the fake was run again, GitHub showed the fake success. |

So anyone who can push a branch can post a `tollgate gate` check that GitHub cannot tell from the real one. The order decides which shows.

What is not shown here: whether the main ruleset's required check `tollgate gate` (app `github-actions`) accepts the fake. To find out, turn the rulesets on with `PYTHONPATH=. python3 -m setup.apply_rulesets tollgate-ai/tollgate`, push to `tg-lab/e3-fake` again, and try to merge #45.

What would close the hole, all outside this repository's plan:

- An organization ruleset that requires the workflow `tollgate.yml` itself to pass. Only organizations have this.
- A push ruleset that blocks changes to `.github/workflows/**` on branches. This needs GitHub Team or Enterprise for a private repository.
- Fewer people with write access. A person who can push a branch can already do this.
