# Changelog

All notable changes to gitundo are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-09-08

Initial release.

### Added

- `gitundo snap` — checkpoint the complete working state (staged, unstaged,
  untracked, deletions, symlinks, binaries) onto the hidden ref
  `refs/gitundo/checkpoints`.
- `gitundo restore` — restore any checkpoint with non-destructive defaults:
  local edits are parked as `*.gitundo-keep`, committed history is never
  touched, untracked files survive unless `--delete-extraneous`.
- `gitundo list`, `gitundo diff`, `gitundo tag` / `gitundo untag` (lightweight
  tag refs under `refs/gitundo/tags/`), `gitundo status`.
- `gitundo prune` — drop old checkpoints, protecting the newest N and tagged
  ones; survivors are re-linked linearly.
- Auto-guard: `gitundo autowrap` installs a bash/zsh wrapper that snapshots
  before clearly destructive commands (`reset --hard`, `clean -dfx`,
  `checkout -f`, `restore`, `rm -rf`, …). Disable anytime with
  `GITUNDO_DISABLE=1`.
- Selectors everywhere: `latest`, numbers (N snapshots ago), tags, oid
  prefixes.
- Checkpoint commits authored `gitundo <gitundo@localhost>` with a
  `snapshot-of:` marker — never impersonate the user.
- `python -m gitundo`, `gitundo -C DIR`, `NO_COLOR` support.
- Machine-readable `--json` output for `snap`, `list` and `status` (stable
  contract used by the editor integration).
- **VS Code extension** under `extensions/vscode/`: GitUndo activity-bar view
  with checkpoint list, one-click snapshot, restore/diff/tag/untag/prune from
  the UI, status-bar counter, and full command palette integration.
- 75+ tests against real throwaway git repositories.
