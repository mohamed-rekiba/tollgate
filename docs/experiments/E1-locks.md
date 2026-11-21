# E1: Locks

**Result: partly run. A workflow can create a tag. The ruleset part was not run.**

## What was run

A workflow on a push to a `tg-lab/e1-*` branch, with `contents: write`, created an annotated tag and pushed it. It then moved the same tag to a new commit and pushed it with force. Run 44843991100, tag `tg-lab/e1-44843991100`.

## What happened

- The tag was created. Its tagger is `github-actions[bot]`.
- The move also succeeded. The tag message reads `moved`, and the tag points at a commit that is on no branch.

The second result is expected: no ruleset was in place. It shows that the ruleset is the only thing that stops a lock from moving.

## What was not run, and why

This session can push branches but cannot push tags, create rulesets, or call the Actions API. Those limits belong to the session, not to the design.

Not run:

1. A ruleset on tags `refs/tags/tg/**` that blocks update and deletion for everyone.
2. The same ruleset blocking creation for everyone except GitHub Actions. Whether GitHub Actions can be a bypass actor on a ruleset of a personal repository is not known.
3. The same steps as a user with write access only.

The owner runs [scripts/e1_rulesets.sh](scripts/e1_rulesets.sh) to finish this experiment.

## What this changes in the plan

The gate cannot trust a freeze tag on its own. It also checks that the tagger is `github-actions[bot]` and that the tag message holds the manifest with the commit it names. A moved tag then fails, because the manifest names a different commit from the one the tag points at. This holds only together with the ruleset.
