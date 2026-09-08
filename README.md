<div align="center">

# 🛟 gitundo

**The undo button git never had.**

Automatic safety‑net snapshots for any git repository — so you can never lose
work to `reset --hard`, `clean -fdx`, a bad rebase, or "oops I deleted it" again.

Zero dependencies · works in any repo · never touches your history.

```
pip install gitundo
```

[![PyPI version](https://img.shields.io/pypi/v/gitundo?color=2dd4bf&label=PyPI)](https://pypi.org/project/gitundo/)
[![Python versions](https://img.shields.io/pypi/pyversions/gitundo?color=2dd4bf)](https://pypi.org/project/gitundo/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2dd4bf.svg)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/xrchris7/gitundo/ci.yml?branch=main&label=CI)](https://github.com/xrchris7/gitundo/actions)
[![VS Code extension](https://img.shields.io/visual-studio-marketplace/v/gitundo.gitundo?color=5b8cff&label=VS%20Code)](https://marketplace.visualstudio.com/items?itemName=gitundo.gitundo)

[Features](#features) · [Quick start](#quick-start) · [Commands](#commands) ·
[Auto-guard](#the-auto-guard) · [How it works](#how-it-works) ·
[Recipes](#recipes) · [Comparison](#comparison) · [FAQ](#faq)

</div>

---

## The one-paragraph pitch

Git only protects work you **commit**. Everything else — the half‑finished
refactor, the deleted file, the unstaged fix that took an hour — is one
`reset --hard` away from oblivion. gitundo is a safety net for exactly that:

* **`gitundo snap`** stores the entire current state of your working tree
  (staged **and** unstaged **and** untracked) as a lightweight *checkpoint*.
* **`gitundo restore`** brings any checkpoint back — even files you deleted.
* The **auto-guard** (`gitundo autowrap`) snapshots automatically before
  destructive commands like `git reset --hard` or `git clean -fdx`.

Checkpoints live on a hidden ref — `refs/gitundo/checkpoints` — so they are
**ordinary git objects**: deduplicated by git, visible in `git log`,
shareable, and safe. Your branches, commits, index and tags are never touched.

---

## Features

| | |
|---|---|
| 📸 **Snapshot anything** | Staged, unstaged, *and* untracked files, deletions, symlinks, binaries. Ignored files and the stash are never captured. |
| 🪂 **Undo the un‑undoable** | Recover files destroyed by `reset --hard`, `clean -fdx`, `checkout -f`, bad merges, editor mishaps — even files that were never committed. |
| 🛡️ **Auto‑guard** | Optional shell wrapper that snapshots *before* clearly destructive git commands. You are always one command from a safety net. |
| 🏷️ **Tag & diff** | Name checkpoints (`gitundo tag demo-ready`), inspect exactly what each one saved (`gitundo diff`). |
| 🔒 **Zero‑invasion** | Only a hidden ref is ever written. The index, working tree, and history stay exactly as they were. |
| 🪶 **Zero dependencies** | Pure standard library. Works everywhere git works. |
| 🚿 **Prune** | `gitundo prune -k 50` keeps your latest 50 (+ tagged) and reclaims the rest. |
| 🧵 **Library + CLI** | Use it from your own scripts via `from gitundo import core`. |
| 🧑‍💻 **VS Code extension** | Official editor integration — sidebar checkpoints, one-click snapshot & restore, diff, tags and a live status bar (see [`extensions/vscode`](extensions/vscode)). |

---

## Quick start

```bash
# 1. install
pip install gitundo          # or: uv tool install gitundo / pipx install gitundo

# 2. snapshot whenever you reach a point you might want to return to
gitundo snap "before the big refactor"

# ...edit files, experiment, break things...

# 3. bring back the state from any snapshot
gitundo list                 # see what you've saved
gitundo restore              # latest snapshot
gitundo restore 2            # two snapshots ago
gitundo restore before-the-big-refactor   # by tag
```

### The one-command setup you'll actually use

```bash
gitundo on        # mark this repo as guarded
gitundo autowrap  # install the shell wrapper (one time, per machine)
```

### Editor integration (VS Code)

The official **gitundo extension** puts a 🛟 GitUndo view in your Activity Bar:
snapshot with one click, browse checkpoints, diff what each one saved, and
restore from the right-click menu — all without touching your commits.

```
git clone https://github.com/xrchris7/gitundo
cd gitundo/extensions/vscode
npm install && npm run package        # -> gitundo-<version>.vsix
code --install-extension gitundo-0.1.0.vsix
```

(Needs the CLI installed: `pip install gitundo`.) Full details in
[`extensions/vscode/README.md`](extensions/vscode/README.md).

Now every time you run a destructive command, gitundo quietly saves a
checkpoint first:

```text
$ git reset --hard HEAD~3
gitundo  snapshot before git reset --hard → 9f3a1c2
HEAD is now at 7b8c9d0 add feature

$ git clean -fdx
gitundo  snapshot before git clean -dfx → 0e5d2b1
Removing build/cache/

# hours later — "wait, that reset was a mistake" →
$ gitundo restore
✔ restored working tree to latest (14 file(s) written, 0 removed)
```

Disable the guard at any moment with `export GITUNDO_DISABLE=1`.

---

## Commands

| Command | What it does |
|---|---|
| `gitundo snap [msg] [-t TAG]` | Snapshot the current working state. |
| `gitundo list [-n N] [--tags]` | List checkpoints, newest first. |
| `gitundo restore [SEL] [--index] [--hard] [--delete-extraneous]` | Restore the working tree to a checkpoint. |
| `gitundo diff [SEL] [--from SEL] [--workdir]` | Show what a snapshot saved, or diff two snapshots. |
| `gitundo tag NAME [SEL]` / `gitundo untag [NAME]` | Give checkpoints readable names. |
| `gitundo prune -k N` | Delete old checkpoints (tagged ones survive). |
| `gitundo status` | Guard state + recent checkpoints + storage used. |
| `gitundo on` / `gitundo off` | Enable/disable the guard for this repo. |
| `gitundo autowrap [--uninstall]` | Install/remove the destructive-command shell wrapper. |
| `gitundo help` | Full command reference. |

**Selectors** — everywhere a checkpoint is expected:

```
latest | N (0 = latest, 1 = the one before…) | a tag name | an object-id prefix
```

Full reference in [`docs/CLI.md`](docs/CLI.md).

---

## The auto-guard

`gitundo autowrap` adds a tiny function to your `~/.bashrc` / `~/.zshrc` that
intercepts `git` and, **only when** the command is clearly destructive,
snapshots first, then runs your command normally (stdin/stdout/exit code all
inherited). Nothing else changes — `git status` is never slowed down.

Currently guarded: `git reset --hard`, `git clean -dfx`, `git checkout -f` /
`--` / `.`, `git restore`, `git rm`, `git branch -D`, `git update-ref`, plus
plain-shell `rm -rf`, `rmdir`, `shred`, `mv`/`cp`, `truncate`, `dd` and
in-place `sed -i`-style edits when run through the wrapped `git`.

> History operations like `merge`, `rebase`, `revert` and `cherry-pick` are
> deliberately **not** guarded: git's own reflog already protects them and they
> never delete uncommitted work — auto-snapshots would only add noise.

---

## How it works

Snapshots are plain commits hanging off a hidden ref:

```text
git commit                                  ← the snapshot
tree  f02a9…  ← complete working state: tracked + untracked files as-is
author    gitundo <gitundo@localhost>       ← never impersonates you
message   before-the-big-refactor           (subject)
          snapshot-of: a1b2c3d              ← your HEAD at capture time
          created-by: gitundo
```

```
refs/gitundo/checkpoints  o3 → o2 → o1 → …   (linear chain of snapshots)
refs/gitundo/tags/demo-ready → o2            (tags are lightweight refs)
```

Because a checkpoint is a real commit, git does the heavy lifting for you:

* **Deduplication is free.** Ten snapshots of an almost-unchanged repo add
  only a few objects — identical file content is stored once, forever.
* **Restore never rewrites history.** It writes files back into your working
  tree. Committed work is left alone (it's already safe).
* **You can inspect them with plain git:** `git log refs/gitundo/checkpoints`
  and even push the ref to back your safety net up on a remote.

### Guarantees

* The working tree, index, branch refs and tags are **never modified** by
  snapshot / list / diff.
* Restore **never deletes** files that exist only in commits newer than the
  checkpoint, and never deletes untracked files (unless you pass
  `--delete-extraneous`).
* Restore **never overwrites** a file with local edits — they are parked as
  `*.gitundo-keep` and reported (pass `--hard` to overwrite instead).
* Snapshot commits are authored `gitundo`, so they are instantly
  recognisable in `git log` and can never be mistaken for (or signed as) your
  work.
* Every command degrades gracefully: if gitundo can't run, your git command
  still runs.

### What gitundo deliberately is not

* Not a backup tool for `.git` itself, and it does not protect *committed*
  history (reflog + remotes already do).
* Not a replacement for good commits — it *protects the stuff between them*.

---

## Recipes

**Recover from `git clean -fdx`** (deleted untracked work):

```bash
gitundo snap            # do this BEFORE you clean
git clean -fdx          # ...or let the auto-guard snapshot for you
# hours later:
gitundo list
gitundo restore 0       # everything is back, as untracked files
```

**Undo a wrong `git reset --hard`** (uncommitted + committed work):

```bash
gitundo snap            # before the reset
git reset --hard HEAD~5
gitundo restore         # working tree is exactly what you snapshotted
git reset --hard <your branch tip>   # then optionally re-point your branch
```

**Branch experiments without fear:**

```bash
gitundo snap exp-start
git checkout -b experiment
# ... go wild ...
git checkout main
gitundo restore exp-start    # clean tree exactly as you left it
```

**Before an AI agent / co-pilot edits your repo:**

```bash
gitundo snap "before agent run"
# let the agent do its thing; if it trashes files, gitundo restore
```

**In CI / scripts** (zero output unless something is wrong):

```bash
gitundo snap -t ${GITHUB_SHA} || true     # snapshot, never fail the build
```

**As a library:**

```python
from gitundo import core

core.snapshot(path=".", message="deploy preflight", tag="pre-deploy")
cps = core.list_checkpoints()
core.restore(path=".", selector="pre-deploy")
```

---

## Comparison

| Tool | What it does | How gitundo differs |
|---|---|---|
| `git stash` | Temporarily shelves a *single* change set | Checkpoints stack: full history of every intermediate state, browseable & restorable by tag/number |
| reflog | Undoes *committed* operations | gitundo protects *uncommitted* state, which reflog can't |
| `ugit` / `gitjk` | Interactive recipe for reversing specific git commands | gitundo is automatic + non-interactive; snapshots include untracked files & deletions |
| `git-snap` | Manual snapshot to a side branch | gitundo: full undo cycle (snap → list → diff → restore), tags, guard, prune |
| `jj` / agents' checkpoints | Continuous op-log / per-session snapshots | gitundo rides on *your* plain git (no new VCS), opt-in per repo, no config |

---

## FAQ

**Does it slow git down?** Only the commands you ask it to guard, and only for
the brief moment a checkpoint is written. Ordinary commands pass straight
through.

**Where does the data live?** In your repo's own `.git` object store, under
`refs/gitundo/`. There is no daemon, no database, nothing to corrupt
independently of git.

**Can I push checkpoints to a remote?** Yes — they're refs:
`git push origin refs/gitundo/checkpoints:refs/gitundo/checkpoints`.

**Is this safe for huge monorepos?** Snapshots reuse git's own content
addressing, so unchanged content costs almost nothing. Files larger than
~64 MB are skipped for byte-comparison during restore (still snapshotted).

**How do I reclaim space?** `gitundo prune -k 20`, then occasionally
`git gc --prune=now`.

**Where are my checkpointed files if the working tree is clean?** If a
snapshot captured nothing new, gitundo says so and stores nothing.

---

## Contributing

Contributions are very welcome — docs, tests, shell guards, integrations
(IDE, pre-commit, Git hooks), and more destructive-command patterns. See
[`CONTRIBUTING.md`](CONTRIBUTING.md). The codebase is intentionally small:

```
src/gitundo/core.py   ~ the engine (snapshot, restore, diff, prune, guard)
src/gitundo/cli.py    ~ the command-line interface
tests/                ~ 75+ tests against real throwaway git repositories
extensions/vscode/    ~ the official VS Code extension (sidebar, commands)
```

## License

[MIT](LICENSE)
