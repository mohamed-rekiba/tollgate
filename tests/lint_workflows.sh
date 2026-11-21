#!/usr/bin/env bash
# Lint the workflow templates with actionlint, with a dummy pin in place.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/.github/workflows"
for f in "$root"/workflows/*.yml; do
  sed 's/__TOLLGATE_REF__/0000000000000000000000000000000000000000/' "$f" \
    > "$tmp/.github/workflows/$(basename "$f")"
done
cd "$tmp" && git init -q && actionlint
echo "workflow templates: ok"
