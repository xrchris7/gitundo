# gitundo CLI reference

`gitundo` is a safety net for git repositories. Snapshots of your working
state are stored as ordinary git commits on the hidden ref
`refs/gitundo/checkpoints`.

```
gitundo [-C DIR] [--version] <command> [args]
```

Global options:

| Option | Meaning |
|---|---|
| `-h, --help` | Show help |
| `--version` | Print version |
| `-C DIR` | Run as if started in DIR (like `git -C`) |

---

## `gitundo snap [MESSAGE] [-m MSG] [-t TAG] [-f]`

Snapshot the current working state.

Captures staged changes, unstaged edits, untracked (non-ignored) files and
deletions — the complete state of everything on disk. Ignored files and the
stash are not captured.

| Flag | Meaning |
|---|---|
| `MESSAGE`, `-m MSG` | A human label (shows up in `gitundo list`) |
| `-t, --tag TAG` | Also tag the new checkpoint |
| `-f, --force` | Create a checkpoint even when nothing changed |

Exit codes: `0` success (or nothing to do), `1` error.

```bash
gitundo snap
gitundo snap "before refactor"
gitundo snap -t deploy-candidate -m "pre-deploy state"
```

## `gitundo list [-n N] [--tags]`

List checkpoints, newest first.

| Flag | Meaning |
|---|---|
| `-n, --limit N` | Show at most N checkpoints |
| `--tags` | Show only tagged checkpoints |

## `gitundo restore [SELECTOR] [--index] [--hard] [--delete-extraneous]`

Restore the working tree to a checkpoint.

Safety rules (always enforced):

* Committed history, branches, tags and HEAD are never modified.
* Files with local edits are never overwritten unless `--hard`. They are
  preserved as `<file>.gitundo-keep` and reported.
* Files that exist only in commits newer than the checkpoint are never
  deleted (they are safe in git already).
* Untracked files are never deleted unless `--delete-extraneous`.

| Flag | Meaning |
|---|---|
| `--index` | Also reset the index to match the checkpoint |
| `--hard` | Overwrite files that have local edits instead of keeping them aside |
| `--delete-extraneous` | Delete untracked files that did not exist in the checkpoint |

```bash
gitundo restore              # latest snapshot
gitundo restore 3            # three snapshots ago
gitundo restore demo-ready   # by tag
gitundo restore a1b2c3d      # by commit prefix
gitundo restore --hard 0     # latest, overwriting local edits
```

## `gitundo diff [SELECTOR] [--from SEL] [--workdir]`

Show what a checkpoint captured.

* Without flags: diff between the checkpoint and the commit you had checked
  out when the snapshot was taken — i.e., exactly the work it saved.
* `--from SEL`: diff between two checkpoints.
* `--workdir`: diff the checkpoint against your current working tree (what a
  restore would change right now).

```bash
gitundo diff
gitundo diff demo-ready
gitundo diff --from 2 0
gitundo diff --workdir
```

## `gitundo tag NAME [SELECTOR]` · `gitundo untag [NAME]`

Tags are lightweight refs under `refs/gitundo/tags/<name>` — they never
rewrite checkpoints and never pollute `git tag`.

```bash
gitundo tag demo-ready          # tag the latest checkpoint
gitundo tag v1 2                # tag two snapshots ago
gitundo list --tags
gitundo untag demo-ready
```

Names: 1–64 characters from `[A-Za-z0-9_.-]`, must start with a letter or
digit, must not end with `.`.

## `gitundo prune [-k N] [--no-tags]`

Delete old checkpoints. Keeps the newest `N` (default 100) plus any tagged
checkpoints. The surviving chain is rewritten linearly; the dropped commits
become unreachable and are reclaimed by a later `git gc`.

```bash
gitundo prune -k 20
gitundo prune -k 0 --no-tags    # dangerous: prunes everything (refused if
                                # it would remove the last checkpoint)
```

## `gitundo status`

Summarise protection state: guard on/off, auto-wrap installed?, recent
checkpoints, storage used.

## `gitundo on` · `gitundo off`

Set/unset the repo-local config flag `gitundo.enabled`. This is a *display
and integration* flag (e.g. for shell prompts); the guard works regardless.

## `gitundo autowrap [--uninstall] [--shell bash|zsh]`

Install or remove the auto-guard shell wrapper in `~/.bashrc` / `~/.zshrc`.

The wrapper defines a `git()` shell function that snapshots *only* before
clearly destructive git commands (see README), then runs your real git
command unchanged. Disable temporarily with `export GITUNDO_DISABLE=1`.

```bash
gitundo autowrap              # install (then open a new shell)
gitundo autowrap --shell zsh
gitundo autowrap --uninstall
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including "nothing to do") |
| 1 | Error (message on stderr) |
| 2 | Usage error |
| 130 | Interrupted (Ctrl-C) |

## Environment

| Variable | Meaning |
|---|---|
| `GITUNDO_DISABLE` | When set (any value), the auto-guard wrapper passes commands straight through without snapshots. |
| `NO_COLOR` | Disable ANSI colours. Colours are also auto-disabled when stdout is not a TTY. |
