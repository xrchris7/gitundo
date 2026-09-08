#!/usr/bin/env bash
#
# set_owner.sh — replace the "<owner>" placeholders throughout the repo
# (README links/badges, pyproject URLs, SECURITY.md, the website and the
# VS Code extension manifest/README) with your real GitHub username.
#
# Usage:   ./scripts/set_owner.sh YOUR_GITHUB_USERNAME
# Example: ./scripts/set_owner.sh alice
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 YOUR_GITHUB_USERNAME" >&2
  exit 1
fi

OWNER="$1"
if [[ ! "$OWNER" =~ ^[A-Za-z0-9-]+$ ]]; then
  echo "error: '$OWNER' does not look like a GitHub username" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FILES=(
  README.md
  PUBLISH.md
  SECURITY.md
  pyproject.toml
  docs/index.html
  extensions/vscode/package.json
  extensions/vscode/README.md
)

count=0
for f in "${FILES[@]}"; do
  if [[ -f "$f" ]] && grep -q "<owner>" "$f"; then
    sed -i "s|<owner>|$OWNER|g" "$f"
    echo "  updated $f"
    count=$((count + 1))
  fi
done

if [[ $count -eq 0 ]]; then
  echo "no '<owner>' placeholders found (already set?)"
else
  echo
  echo "done — replaced <owner> with '$OWNER' in $count file(s)."
  echo "Next:  git add -A && git commit -m 'chore: set owner metadata'"
fi
