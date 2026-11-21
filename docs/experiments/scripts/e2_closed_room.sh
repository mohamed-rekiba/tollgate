#!/bin/sh
# E2: run Claude Code in a container on a fresh copy of a repository.
# Needs: docker or podman, an image with Claude Code (build one from node:22
# with `npm install -g @anthropic-ai/claude-code`), and ANTHROPIC_API_KEY or
# CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`).
# Usage: sh e2_closed_room.sh <path to a git repository> <image>
set -eu
SRC="$1"; IMAGE="$2"
RUN=${CONTAINER:-docker}
WORK=$(mktemp -d)
git clone -q --no-hardlinks "$SRC" "$WORK/copy"
git -C "$WORK/copy" remote remove origin
"$RUN" run --rm --network bridge \
  -e ANTHROPIC_API_KEY -e CLAUDE_CODE_OAUTH_TOKEN \
  -v "$WORK/copy:/work" -w /work "$IMAGE" \
  claude -p "Add the line 'e2 was here' to the end of README.md." \
    --output-format json --allowedTools "Read,Edit,Write" > "$WORK/out.json"
python3 - "$WORK/out.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print("parsed as data: yes")
print("cost field:", "total_cost_usd" in data, data.get("total_cost_usd"))
PY
grep -q "e2 was here" "$WORK/copy/README.md" && echo "file changed: yes"
"$RUN" run --rm -v "$WORK/copy:/work" -w /work "$IMAGE" \
  sh -c 'git push 2>&1 || echo "push failed: yes"'
echo "copy kept at $WORK"
