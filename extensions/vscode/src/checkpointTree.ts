/**
 * Sidebar tree: every checkpoint in the active repository, newest first.
 */

import * as path from "path";
import * as vscode from "vscode";

import { Checkpoint, GitUndoCli } from "./cli";
import { Controller } from "./extension";

export class CheckpointNode {
  constructor(
    readonly cp: Checkpoint,
    readonly root: string,
  ) {}
}

/** Commands are wired with a node argument; resolve it defensively. */
export function repoNodeFromArgs(args: unknown): { cp: Checkpoint; root: string } | undefined {
  if (args && typeof args === "object" && args instanceof CheckpointNode) {
    return { cp: args.cp, root: args.root };
  }
  const maybe = args as { cp?: Checkpoint; root?: string } | undefined;
  if (maybe?.cp && maybe?.root) {
    return { cp: maybe.cp, root: maybe.root };
  }
  return undefined;
}

function timeAgo(ts: number): string {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000) - ts);
  if (seconds < 60) {
    return "just now";
  }
  if (seconds < 3600) {
    return `${Math.floor(seconds / 60)}m ago`;
  }
  if (seconds < 86400) {
    return `${Math.floor(seconds / 3600)}h ago`;
  }
  return `${Math.floor(seconds / 86400)}d ago`;
}

export class CheckpointsProvider implements vscode.TreeDataProvider<CheckpointNode> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    CheckpointNode | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private view: vscode.TreeView<CheckpointNode> | undefined;

  constructor(private readonly controller: Controller) {}

  attachTreeView(view: vscode.TreeView<CheckpointNode>): void {
    this.view = view;
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  async getTreeItem(node: CheckpointNode): Promise<vscode.TreeItem> {
    const item = new vscode.TreeItem(
      node.cp.tag
        ? { label: node.cp.tag, highlights: undefined }
        : { label: node.cp.message || node.cp.short, highlights: undefined },
      vscode.TreeItemCollapsibleState.None,
    );
    item.id = `${node.root}::${node.cp.id}`;
    item.iconPath = node.cp.tag
      ? new vscode.ThemeIcon("tag")
      : new vscode.ThemeIcon("history");
    item.description = `${node.cp.short} · ${timeAgo(node.cp.timestamp)}`;
    item.tooltip = new vscode.MarkdownString(
      [
        `**${node.cp.message || node.cp.short}**`,
        "",
        `- id: \`${node.cp.id}\``,
        node.cp.tag ? `- tag: \`${node.cp.tag}\`` : "",
        `- saved: ${node.cp.when}`,
        node.cp.snapshot_of && node.cp.snapshot_of !== "(unborn)"
          ? `- from commit: \`${node.cp.snapshot_of.slice(0, 7)}\``
          : "",
      ]
        .filter(Boolean)
        .join("\n"),
    );
    item.contextValue = node.cp.tag ? "tagged" : "checkpoint";
    item.command = {
      command: "gitundo.diff",
      title: "Diff checkpoint",
      arguments: [node],
    };
    return item;
  }

  async getChildren(): Promise<CheckpointNode[]> {
    const root = this.controller.activeRoot();
    const repoName = root ? path.basename(root) : "";
    if (!root) {
      this.view && (this.view.message = "Open a folder that is inside a git repository.");
      return [];
    }
    const handle = this.controller.cli();
    if (!handle) {
      this.view && (this.view.message = "");
      return [];
    }
    try {
      const cps = await handle.list();
      if (this.view) {
        this.view.message =
          cps.length === 0
            ? `No checkpoints in “${repoName}” yet — press the ➕ button or run \`gitundo snap\`.`
            : undefined;
      }
      return cps.map((cp) => new CheckpointNode(cp, handle.repoRoot));
    } catch {
      if (this.view) {
        this.view.message =
          "gitundo CLI not found.\n\nInstall with:  pip install gitundo\n" +
          "Then reload this window (or set the path in settings → gitundo.cliPath).";
      }
      return [];
    }
  }

  getParent(): vscode.ProviderResult<CheckpointNode> {
    return null;
  }
}
