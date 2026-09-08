# gitundo architecture & design notes

gitundo is intentionally small. This document explains the invariants that
make it safe, so contributors do not accidentally break them.

```
┌────────────┐      ┌────────────────────────────────────────────┐
│  gitundo   │      │  your repository (.git)                     │
│  CLI /     │─────▶│                                            │
│  wrapper   │      │  refs/gitundo/checkpoints  → o4 → o3 → …   │
│            │      │  refs/gitundo/tags/*       → lightweight    │
│            │      │                            tag pointers     │
└────────────┘      │  your branches / index / working tree       │
                    │       ↑ never modified by snapshotting      │
                    └────────────────────────────────────────────┘
```

## The core trick: checkpoints are commits

A snapshot is a normal git commit whose *tree* is the complete state of
everything on disk (tracked files as they are, plus untracked non-ignored
files), whose *parent* is the previous snapshot, and which is only reachable
from the hidden ref `refs/gitundo/checkpoints`.

Consequences (all intentional):

1. **Deduplication is free.** git's object database stores each blob/tree
   once. Ten snapshots of the same repo cost almost nothing.
2. **Nothing extra to corrupt.** There is no side database; snapshots share
   the integrity model of git itself.
3. **They are inspectable with plain git.** `git log refs/gitundo/checkpoints`
   works; the ref can even be pushed to a remote.
4. **Identity is honest.** Snapshot commits are authored
   `gitundo <gitundo@localhost>`, and each message records `snapshot-of:`
   = your HEAD at capture time.

## Building a snapshot tree (never touches the real index)

`core._build_tree()` writes into a throwaway index file
(`.gitundo-tmp-index-<pid>`, deleted in a `finally`):

1. `read-tree HEAD` (or the empty tree if the repo is unborn);
2. `update-index --add --remove --stdin -z` with every path that differs
   from HEAD *or* is untracked — present files are read from disk, missing
   files are dropped;
3. `write-tree` → the snapshot tree.

The result is a faithful "state of the working directory" snapshot that also
reflects staged content and deletions. Then `commit-tree` + `update-ref`
atomically extends the chain.

## Non-invasiveness contract

| Operation        | Working tree | Index | Branches/tags/HEAD |
|------------------|:------------:|:-----:|:------------------:|
| `snap`           | never        | never | never              |
| `list`/`diff`    | never        | never | never              |
| `restore`        | writes back  | only with `--index` | never |
| `prune`          | never        | never | never (checkpoint chain only) |

## Restore safety rules

Restoring rewinds your *working tree* only, and refuses to do anything that
could silently destroy data:

* **History is untouchable.** Commits newer than the checkpoint that exist in
  HEAD are never deleted — they are safe in git already.
* **Local edits are never lost.** A file whose on-disk content differs from
  both the checkpoint and its `snapshot-of:` base is parked as
  `<file>.gitundo-keep` and reported; `--hard` opts into overwriting.
* **Untracked files survive** unless `--delete-extraneous` is passed.
* Conflict detection compares *blob hashes* (`git hash-object`) rather than
  reading files into Python, so it is fast and exact. Files > 64 MB are
  always treated as "possibly edited" (parked, never clobbered).

## Guard design (conservative by construction)

`core.DESTRUCTIVE_PATTERNS` matches *full command lines* with explicit,
unambiguous destructive markers (`--hard`, `-dfx`, `-f`, `rm -r`, `-i`, …).
History-only operations (`merge`, `rebase`, `revert`, `cherry-pick`) are
deliberately excluded: the reflog already protects committed work, and they
cannot delete uncommitted changes — auto-snapshotting them would only add
noise and slow down normal workflows.

The shell wrapper (`gitundo autowrap`) defines a `git()` function so the
guard only ever sees invocations of *git*, not every command in the shell.
`GITUNDO_DISABLE=1` bypasses it entirely. If anything inside gitundo fails,
the real git command still runs — the guard never blocks the user.

## Selectors

`latest` / `@` / `0` → newest checkpoint. Integer `N` → the Nth snapshot back
(`1` = one before latest). Tag names and oid prefixes resolve too.
Checkpoint ordering is taken from `git log --reverse` on the ref — i.e. the
chain topology — because multiple snapshots within the same second otherwise
share an identical timestamp and become unorderable.

## Prune

Pruning rewrites the surviving checkpoint commits into a fresh linear chain
and moves `refs/gitundo/tags/*` from old to new oids. Dropped commits become
unreachable and are reclaimed by a later `git gc`. Tagged checkpoints and the
newest `-k` (default 100) are always protected.
