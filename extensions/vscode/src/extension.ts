/**
 * gitundo for VS Code — activation and command wiring.
 *
 * Architecture:
 *   extension.ts        controllers: active-repo resolution, commands, status bar
 *   cli.ts              typed wrapper around the `gitundo` CLI (JSON protocol)
 *   checkpointTree.ts   sidebar tree of checkpoints
 *   timelineProvider.ts checkpoints shown in the editor Timeline panel
 */

import * as path from "path";
import * as vscode from "vscode";

import { Checkpoint, CliError, GitUndoCli } from "./cli";
import { CheckpointsProvider, repoNodeFromArgs } from "./checkpointTree";
import { GitUndoStatusBar } from "./statusBar";

let output: vscode.OutputChannel | undefined;

function log(line: string): void {
  output ??= vscode.window.createOutputChannel("gitundo");
  output.appendLine(line);
}

/**
 * Owns the CLI handles for each workspace folder and resolves the "active"
 * repository (the folder of the focused editor, else the first folder).
 */
export class Controller {
  readonly configuredPath: string;
  private readonly cliByRoot = new Map<string, GitUndoCli>();

  constructor() {
    this.configuredPath =
      vscode.workspace.getConfiguration("gitundo").get<string>("cliPath", "") ?? "";
  }

  activeRoot(): string | undefined {
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      const hit = this.rootForUri(editor.document.uri);
      if (hit) {
        return hit;
      }
    }
    const folders = vscode.workspace.workspaceFolders ?? [];
    if (folders.length > 0) {
      return folders[0].uri.fsPath;
    }
    return undefined;
  }

  rootForUri(uri: vscode.Uri): string | undefined {
    const folders = vscode.workspace.workspaceFolders ?? [];
    for (const folder of folders) {
      if (
        uri.fsPath === folder.uri.fsPath ||
        uri.fsPath.startsWith(folder.uri.fsPath + path.sep)
      ) {
        return folder.uri.fsPath;
      }
    }
    return undefined;
  }

  /** CLI handle for the active repo (or the folder owning *uri*). */
  cli(uri?: vscode.Uri): GitUndoCli | undefined {
    const root = uri ? this.rootForUri(uri) : this.activeRoot();
    if (!root) {
      return undefined;
    }
    let handle = this.cliByRoot.get(root);
    if (!handle) {
      handle = new GitUndoCli(root, this.configuredPath);
      this.cliByRoot.set(root, handle);
    }
    return handle;
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const controller = new Controller();
  const provider = new CheckpointsProvider(controller);

  const treeView = vscode.window.createTreeView("gitundo.checkpoints", {
    treeDataProvider: provider,
    showCollapseAll: true,
  });
  provider.attachTreeView(treeView);
  context.subscriptions.push(treeView);

  const statusBar = new GitUndoStatusBar(controller, provider);
  statusBar.attach(context);

  async function refreshAll(): Promise<void> {
    provider.refresh();
    await statusBar.refresh();
  }

  // ------------------------------------------------------------------ snap
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.snap", async () => {
      const handle = controller.cli();
      if (!handle) {
        vscode.window.showWarningMessage(
          "gitundo: open a folder inside a git repository first.",
        );
        return;
      }
      const message = await vscode.window.showInputBox({
        prompt: "Snapshot message (optional)",
        placeHolder: "e.g. before the big refactor",
        ignoreFocusOut: true,
      });
      if (message === undefined) {
        return;
      }
      let tag: string | undefined;
      const wantTag = await vscode.window.showQuickPick(["Yes, tag it", "No tag"], {
        placeHolder: "Add a tag to this checkpoint?",
        ignoreFocusOut: true,
      });
      if (wantTag === "Yes, tag it") {
        tag = await vscode.window.showInputBox({
          prompt: "Tag name",
          placeHolder: "e.g. demo-ready",
          validateInput: (value) =>
            /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(value)
              ? undefined
              : "Letters, digits and . _ - (start with a letter or digit)",
          ignoreFocusOut: true,
        });
        if (tag === undefined) {
          return;
        }
      }
      try {
        const cp = await handle.snap(message ?? undefined, tag);
        vscode.window.setStatusBarMessage(`gitundo: checkpoint ${cp.short} saved`, 4000);
      } catch (err) {
        showCliError(err, "snapshot");
      }
      await refreshAll();
    }),
  );

  // --------------------------------------------------------------- restore
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.restore", async (node) => {
      const selection = await resolveSelection(controller, node);
      if (!selection) {
        return;
      }
      const { cp, handle } = selection;
      const choice = await vscode.window.showWarningMessage(
        `Restore the working tree to checkpoint “${labelFor(cp)}” (${cp.short})?\n\n` +
          "Committed history is never touched. Files with local edits are kept " +
          "aside as *.gitundo-keep, not overwritten.",
        { modal: true },
        "Restore",
        "Restore & overwrite local edits",
      );
      if (!choice) {
        return;
      }
      try {
        const report = await handle.restore(cp.id, { hard: choice.includes("overwrite") });
        vscode.window.showInformationMessage(
          `gitundo: restored working tree to ${cp.short}.` +
            (/kept aside/i.test(report) ? " Local edits were preserved as *.gitundo-keep." : ""),
        );
        log(report);
      } catch (err) {
        showCliError(err, "restore");
      }
      await refreshAll();
    }),
  );

  // ------------------------------------------------------------------ diff
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.diff", async (node) => {
      const selection = await resolveSelection(controller, node);
      if (!selection) {
        return;
      }
      const { cp, handle } = selection;
      try {
        const text = await handle.diffSaved(cp.id);
        const content =
          (text && text.trim() ? text : "(this checkpoint captured a clean tree — nothing to diff)\n");
        const doc = await vscode.workspace.openTextDocument({ content, language: "diff" });
        await vscode.window.showTextDocument(doc, { preview: true });
        log(`diff for ${cp.short} (${cp.id})`);
      } catch (err) {
        showCliError(err, "diff");
      }
    }),
  );

  // ------------------------------------------------------------------ tag
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.tag", async (node) => {
      const selection = await resolveSelection(controller, node);
      if (!selection) {
        return;
      }
      const { cp, handle } = selection;
      const name = await vscode.window.showInputBox({
        prompt: `Tag name for ${cp.short}`,
        placeHolder: "e.g. demo-ready",
        validateInput: (value) =>
          /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/.test(value)
            ? undefined
            : "Letters, digits and . _ - (start with a letter or digit)",
        ignoreFocusOut: true,
      });
      if (!name) {
        return;
      }
      try {
        await handle.tag(name, cp.id);
        vscode.window.showInformationMessage(`gitundo: tagged ${cp.short} as ${name}.`);
      } catch (err) {
        showCliError(err, "tag");
      }
      await refreshAll();
    }),
  );

  // ---------------------------------------------------------------- untag
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.untag", async (node) => {
      const selection = await resolveSelection(controller, node);
      if (!selection) {
        return;
      }
      const { handle } = selection;
      const tagged = (await safeList(handle)).filter((cp) => cp.tag);
      if (tagged.length === 0) {
        vscode.window.showInformationMessage("gitundo: no tagged checkpoints.");
        return;
      }
      const chosen = await vscode.window.showQuickPick(
        tagged.map((cp) => ({
          label: `$(tag) ${cp.tag}`,
          description: `${cp.short} · ${cp.when}`,
          cp,
        })),
        { placeHolder: "Remove which tag?" },
      );
      if (!chosen) {
        return;
      }
      try {
        await handle.untag(chosen.cp.tag);
        vscode.window.showInformationMessage(
          `gitundo: removed tag ${chosen.cp.tag} from ${chosen.cp.short}.`,
        );
      } catch (err) {
        showCliError(err, "untag");
      }
      await refreshAll();
    }),
  );

  // ----------------------------------------------------------------- prune
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.prune", async () => {
      const handle = controller.cli();
      if (!handle) {
        return;
      }
      const keep = await vscode.window.showInputBox({
        prompt: "Keep the newest N checkpoints (tagged ones always survive)",
        value: "100",
        validateInput: (value) => (/^\d+$/.test(value) ? undefined : "Enter a number"),
        ignoreFocusOut: true,
      });
      if (!keep) {
        return;
      }
      try {
        const report = await handle.prune(Number(keep));
        vscode.window.showInformationMessage(
          "gitundo: " + (report || "old checkpoints pruned."),
        );
      } catch (err) {
        showCliError(err, "prune");
      }
      await refreshAll();
    }),
  );

  // ---------------------------------------------------------------- status
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.status", async () => {
      const handle = controller.cli();
      if (!handle) {
        vscode.window.showWarningMessage("gitundo: no workspace folder in a git repository.");
        return;
      }
      try {
        const info = await handle.status();
        if (!info) {
          throw new CliError("gitundo returned no status.", 1, "");
        }
        log(
          `repository:  ${handle.repoLabel}\n` +
            `gitundo:     v${info.version}\n` +
            `guard:       ${info.enabled ? "on" : "off"}\n` +
            `auto-wrap:   ${info.autowrapped ? "installed" : "not installed"}\n` +
            `head:        ${info.head ? info.head.slice(0, 7) : "(unborn)"}\n` +
            `checkpoints: ${info.count}\n`,
        );
        for (const cp of info.recent) {
          log(`   ${cp.short}   ${cp.tag ? `[${cp.tag}]  ` : ""}${cp.message}`);
        }
        output?.show(true);
      } catch (err) {
        showCliError(err, "status");
      }
    }),
  );

  // ---------------------------------------------------------------- refresh
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.refresh", async () => {
      await refreshAll();
      vscode.window.setStatusBarMessage("gitundo: refreshed", 1500);
    }),
  );

  // ---------------------------------------------------------- open terminal
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.openInTerminal", async () => {
      const handle = controller.cli();
      if (!handle) {
        return;
      }
      const terminal = vscode.window.createTerminal({
        name: "gitundo",
        cwd: vscode.Uri.file(handle.repoRoot),
      });
      terminal.sendText("gitundo list");
      terminal.show();
    }),
  );

  // --------------------------------------------------------------- copy id
  context.subscriptions.push(
    vscode.commands.registerCommand("gitundo.copyId", async (node) => {
      const { cp } = repoNodeFromArgs(node) ?? { cp: undefined };
      if (!cp) {
        return;
      }
      await vscode.env.clipboard.writeText(cp.id);
      vscode.window.setStatusBarMessage("gitundo: checkpoint id copied", 2000);
    }),
  );

  // --------------- refresh on file / folder / config change ----------------
  void refreshAll();
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => void refreshAll()),
    vscode.workspace.onDidChangeWorkspaceFolders(() => void refreshAll()),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("gitundo")) {
        void refreshAll();
      }
    }),
  );
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function safeList(handle: GitUndoCli): Promise<Checkpoint[]> {
  try {
    return await handle.list();
  } catch {
    return [];
  }
}

type Selection = { cp: Checkpoint; handle: GitUndoCli };

/** Command came from a tree node → use that checkpoint; else offer a picker. */
async function resolveSelection(controller: Controller, node: unknown): Promise<Selection | undefined> {
  const fromNode = repoNodeFromArgs(node);
  if (fromNode) {
    return {
      cp: fromNode.cp,
      handle: new GitUndoCli(fromNode.root, controller.configuredPath),
    };
  }
  const handle = controller.cli();
  if (!handle) {
    return undefined;
  }
  const list = await safeList(handle);
  if (list.length === 0) {
    vscode.window.showInformationMessage(
      "gitundo: no checkpoints yet. Use “GitUndo: Snapshot working state” first.",
    );
    return undefined;
  }
  const chosen = await vscode.window.showQuickPick(
    list.map((cp) => ({
      label: cp.tag ? `$(tag) ${cp.tag}` : labelFor(cp),
      description: `${cp.short} · ${cp.when}`,
      cp,
    })),
    { placeHolder: "Which checkpoint?" },
  );
  if (!chosen) {
    return undefined;
  }
  return { cp: chosen.cp, handle };
}

function labelFor(cp: Checkpoint): string {
  return cp.message || cp.short;
}

function showCliError(err: unknown, what: string): void {
  if (err instanceof CliError) {
    vscode.window.showErrorMessage(`gitundo ${what} failed.\n\n${err.message}`);
    log(`${err.message}\n${err.stderr}`);
  } else {
    const detail = err instanceof Error ? err.message : String(err);
    vscode.window.showErrorMessage(`gitundo ${what} failed: ${detail}`);
  }
}

export function deactivate(): void {
  /* nothing to clean up */
}
