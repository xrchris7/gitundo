/**
 * Status bar indicator: how many checkpoints exist and whether the guard is
 * on, for the active repository. Clicking opens the gitundo status log.
 */

import * as vscode from "vscode";

import { Controller } from "./extension";
import { CheckpointsProvider } from "./checkpointTree";

export class GitUndoStatusBar implements vscode.Disposable {
  private item: vscode.StatusBarItem | undefined;
  private timer: NodeJS.Timeout | undefined;

  constructor(
    private readonly controller: Controller,
    private readonly provider: CheckpointsProvider,
  ) {}

  attach(context: vscode.ExtensionContext): void {
    this.item = vscode.window.createStatusBarItem("gitundo", vscode.StatusBarAlignment.Left, 60);
    this.item.command = "gitundo.status";
    this.item.tooltip = "gitundo — click for status";
    context.subscriptions.push(this.item, this);
    void this.refresh();
    // gentle polling keeps the counter honest when files change outside VS Code
    this.timer = setInterval(() => void this.refresh(), 60_000);
  }

  async refresh(): Promise<void> {
    const handle = this.controller.cli();
    if (!handle || !this.item) {
      this.item?.hide();
      return;
    }
    try {
      const info = await handle.status();
      if (!info) {
        this.item.hide();
        return;
      }
      const glyph = info.enabled ? "$(shield)" : "$(history)";
      const label = `${glyph} gitundo ${info.count}`;
      this.item.text = label;
      this.item.tooltip =
        `gitundo — ${info.count} checkpoint(s) in ${handle.repoLabel}\n` +
        `guard: ${info.enabled ? "on" : "off"}` +
        `  ·  auto-wrap: ${info.autowrapped ? "installed" : "not installed"}\n` +
        (info.recent[0]
          ? `latest: ${info.recent[0].tag || info.recent[0].message || info.recent[0].short} (${info.recent[0].short})`
          : "no checkpoints yet — run gitundo snap");
      this.item.show();
    } catch {
      this.item.hide();
    }
  }

  dispose(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
    this.item?.dispose();
    this.item = undefined;
  }
}
