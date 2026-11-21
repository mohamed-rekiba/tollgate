#!/bin/sh
# E1, the part that needs an admin: rulesets on the tags under tg/.
# Run as the owner of the repository: sh e1_rulesets.sh owner/repo
set -eu
R="$1"
echo "Creating a ruleset that blocks update and deletion of tags under tg/."
gh api "repos/$R/rulesets" -X POST --input - <<JSON
{"name":"tollgate-locks","target":"tag","enforcement":"active",
 "conditions":{"ref_name":{"include":["refs/tags/tg/**"],"exclude":[]}},
 "rules":[{"type":"update"},{"type":"deletion"},{"type":"non_fast_forward"}]}
JSON
echo "Now push a tag tg/lab-1 by hand, then try: git push -f origin <new commit>:refs/tags/tg/lab-1"
echo "Expected: the forced push is rejected."
echo "Then add a creation rule with GitHub Actions as the only bypass actor, and record whether GitHub accepts it."
