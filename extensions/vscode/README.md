# gitundo for Visual Studio Code

**The undo button git never had — now with a face.**

[gitundo](https://github.com/<owner>/gitundo) snapshots your complete working
state (staged **and** unstaged **and** untracked files) as lightweight git
checkpoints. This extension puts that safety net right in your editor: take a
snapshot, browse your history, and restore files you thought were gone —
without ever touching your commits or branches.

> Requires the **gitundo CLI** to be installed: `pip install gitundo`
> (or `pipx install gitundo`). If it's not on your `PATH`, set the absolute
> path in Settings → `gitundo.cliPath`.

![gitundo in the activity bar](https://raw.githubusercontent.com/<owner>/gitundo/main/extensions/vscode/resources/gitundo-icon.png)

## Features

- **Snap** — one click (or `Ctrl/Cmd+Shift+P` → “GitUndo: Snapshot working
  state”) stores the whole working tree, including untracked files.
- **Restore** — right-click any checkpoint in the GitUndo sidebar and restore
  it. A confirm dialog reminds you that local edits are *kept aside*, never
  clobbered, unless you explicitly choose to overwrite.
- **Diff** — see exactly what a checkpoint captured, as a unified diff.
- **Tag & untag** — name the important moments (`demo-ready`) so they are easy
  to find and are never pruned.
- **Status bar** — a live `gitundo · N` counter shows how many checkpoints your
  current repository has; click it for full status.
- **Prune** — keep your history tidy from the Command Palette.
- **Auto-guard reminder** — the extension tells you how to enable automatic
  snapshots before destructive commands in the terminal
  (`gitundo autowrap`).

## Getting started

1. Install the CLI: `pip install gitundo`
2. Install this extension from the Marketplace (or run the `.vsix`):
   `code --install-extension gitundo-0.1.0.vsix`
3. Open a folder that is a git repository. The 🛟 **GitUndo** view appears in
   the Activity Bar.
4. Click **＋ Snapshot**, type a message like `before the big refactor`, and
   keep coding without fear.

> Even without the extension, everything you do here is 100% compatible with
> the terminal workflow — checkpoints are ordinary git objects.

## Commands

| Command | Description |
|---|---|
| `GitUndo: Snapshot working state` | Store the current working tree as a checkpoint (optionally tagged) |
| `GitUndo: Restore checkpoint…` | Restore a chosen checkpoint back into the working tree |
| `GitUndo: Diff checkpoint vs worktree` | Show the saved diff for a checkpoint |
| `GitUndo: Tag checkpoint…` / `Remove tag…` | Manage checkpoint tags |
| `GitUndo: Prune old checkpoints…` | Keep the newest N checkpoints (+ tagged) |
| `GitUndo: Status` | Guard state, CLI version, recent checkpoints |
| `GitUndo: Open in terminal` | Run `gitundo list` in the integrated terminal |
| `GitUndo: Refresh` | Reload checkpoints for the active repo |

Right-click a checkpoint in the sidebar for **Restore / Diff / Tag / Copy id**.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `gitundo.cliPath` | `""` | Absolute path to the `gitundo` executable. Empty = search `PATH`, then `python3 -m gitundo`. |

## Development

```bash
cd extensions/vscode
npm install
npm run compile        # type-check & build to out/
code .                 # then press F5 to launch the Extension Development Host
npm run package        # produce gitundo-<version>.vsix
```

Run the Python test-suite from the repository root to keep the CLI JSON
contract (which this extension depends on) stable:

```bash
python -m pytest
```

## Release / publishing

```bash
npx vsce publish --pat <MARKETPLACE_TOKEN>    # after `vsce login <publisher>`
```

The publisher id is `gitundo`. CI builds the `.vsix` on every push and can be
configured to publish automatically on tags (see
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)).

## License

MIT — see [LICENSE](../../LICENSE).
