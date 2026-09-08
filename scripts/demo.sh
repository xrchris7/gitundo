#!/usr/bin/env bash
#
# gitundo demo — run an end-to-end story in a throwaway repo.
#
# Usage:
#   ./scripts/demo.sh             # use the installed gitundo binary
#   ./scripts/demo.sh --source    # use ./src via PYTHONPATH (for dev)
#
set -euo pipefail

if [[ "${1:-}" == "--source" ]]; then
  export PYTHONPATH="$(cd "$(dirname "$0")/.." && pwd)/src"
  GU() { python3 -m gitundo "$@"; }
else
  GU() { command gitundo "$@"; }
fi

DEMO_DIR="$(mktemp -d)"
trap 'rm -rf "$DEMO_DIR"' EXIT
cd "$DEMO_DIR"

BOLD=$'\e[1m'; DIM=$'\e[2m'; GREEN=$'\e[32m'; RESET=$'\e[0m'
step() { printf "\n${BOLD}$ %s${RESET}\n" "$*"; }

git init -q .
git config user.email demo@example.com
git config user.name "Demo"
git config commit.gpgsign false

printf 'gitundo — the undo button git never had.\n\nToday:\n- ship feature X\n' > NOTES.md
git add -A
git commit -qm "initial notes"

step "edit files (uncommitted work: a tracked edit + a new untracked draft)"
printf 'Feature X draft:\n- step 1: checkpoint\n- step 2: never lose work\n' > draft.md
printf -- '- step 3: restore anything\n' >> NOTES.md
echo "  tracked edit:  NOTES.md += 'step 3'"
echo "  untracked:     draft.md"

step "gitundo snap -t demo 'before the big refactor'"
GU snap -t demo "before the big refactor"

step "disaster: git checkout -- . && git clean -fdx"
git checkout -- . >/dev/null 2>&1
git clean -fdx >/dev/null 2>&1 || true
echo "  tracked edits reverted, draft.md deleted. Oh no."

step "gitundo list   (your safety net remembers)"
GU list

step "gitundo diff   (exactly what the snapshot saved)"
GU diff | sed -n '1,9p'

step "gitundo restore demo   (by tag)"
GU restore demo

step "everything is back:"
echo "  draft.md    -> $(test -f draft.md && echo present || echo MISSING)"
echo "  NOTES.md    -> $(tail -1 NOTES.md)"

printf "\n${GREEN}Nothing was lost. Ever. 🛟${RESET}\n"
