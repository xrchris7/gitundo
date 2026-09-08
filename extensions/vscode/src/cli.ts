/**
 * Thin, typed wrapper around the `gitundo` command-line tool.
 *
 * The extension talks to gitundo by spawning the CLI (same engine the shell
 * guard uses) and parsing its stable `--json` output. This keeps the editor
 * integration honest: it can never diverge from what the CLI actually does.
 */

import { execFile } from "child_process";
import * as os from "os";
import * as path from "path";

/** A single checkpoint as reported by `gitundo list --json`. */
export interface Checkpoint {
  id: string;
  short: string;
  tag: string;
  message: string;
  when: string;
  timestamp: number;
  snapshot_of: string;
}

/** `gitundo status --json` payload. */
export interface StatusInfo {
  version: string;
  enabled: boolean;
  autowrapped: boolean;
  head: string;
  count: number;
  recent: Checkpoint[];
}

export interface CliResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** Result of resolving which command invocation provides gitundo. */
export interface CliResolution {
  argv: string[];
  label: string;
}

export class CliError extends Error {
  constructor(
    message: string,
    public readonly code: number,
    public readonly stderr: string,
  ) {
    super(message);
    this.name = "CliError";
  }
}

/**
 * Return the list of possible ways to invoke gitundo, most preferred first.
 * A configured `cliPath` wins; otherwise PATH lookup of the `gitundo` binary
 * and, as a fallback, `python3 -m gitundo`.
 */
export function cliCandidates(configuredPath: string): CliResolution[] {
  const out: CliResolution[] = [];
  if (configuredPath && configuredPath.trim()) {
    const p = configuredPath.trim();
    out.push({ argv: [p], label: p });
  }
  out.push({ argv: ["gitundo"], label: "gitundo (PATH)" });
  if (os.platform() !== "win32") {
    out.push({ argv: ["python3", "-m", "gitundo"], label: "python3 -m gitundo" });
  }
  return out;
}

/** Run one candidate quickly (--version) to see if it exists and works. */
function candidateWorks(argv: string[]): Promise<boolean> {
  return new Promise((resolvePromise) => {
    const child = execFile(
      argv[0],
      [...argv.slice(1), "--version"],
      { cwd: os.tmpdir(), timeout: 4000, windowsHide: true },
      (err) => resolvePromise(!err),
    );
    child.unref?.();
  });
}

export async function resolveCli(configuredPath: string): Promise<CliResolution> {
  const errors: string[] = [];
  for (const candidate of cliCandidates(configuredPath)) {
    try {
      if (await candidateWorks(candidate.argv)) {
        return candidate;
      }
    } catch {
      /* try next */
    }
  }
  throw new CliError(
    "Could not find the `gitundo` command line tool.\n\n" +
      "Install it first:  pip install gitundo   (or  pipx install gitundo)\n" +
      "Then reload this window. You can also set the absolute path in " +
      "settings under `gitundo.cliPath`.\n\n" +
      "Details: " + (errors.join("; ") || "no candidate responded to `gitundo --version`."),
    127,
    "",
  );
}

function run(
  argv: string[],
  args: string[],
  cwd: string,
): Promise<CliResult> {
  return new Promise((resolvePromise, reject) => {
    execFile(
      argv[0],
      [...argv.slice(1), ...args],
      {
        cwd,
        timeout: 30_000,
        maxBuffer: 8 * 1024 * 1024,
        windowsHide: true,
        env: { ...process.env, NO_COLOR: "1" },
      },
      (err, stdout, stderr) => {
        if (err) {
          const code = typeof (err as { code?: unknown }).code === "number"
            ? ((err as { code: number }).code)
            : 1;
          resolvePromise({ code, stdout, stderr });
          return;
        }
        resolvePromise({ code: 0, stdout, stderr });
      },
    );
  });
}

function parseJson<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

/**
 * Programmatic handle on gitundo for one repository folder.
 */
export class GitUndoCli {
  private resolution: CliResolution | null = null;
  private resolutionError: string | null = null;

  constructor(
    readonly repoRoot: string,
    private readonly configuredPath: string,
  ) {}

  get repoLabel(): string {
    return path.basename(this.repoRoot);
  }

  /** Cached command resolution; throws CliError if nothing usable. */
  async argv(): Promise<string[]> {
    if (this.resolution) {
      return this.resolution.argv;
    }
    try {
      this.resolution = await resolveCli(this.configuredPath);
    } catch (err) {
      this.resolutionError = err instanceof Error ? err.message : String(err);
      throw err;
    }
    return this.resolution.argv;
  }

  async exec(args: string[]): Promise<CliResult> {
    const argv = await this.argv();
    const result = await run(argv, args, this.repoRoot);
    if (result.code !== 0 && result.code !== 1) {
      throw new CliError(
        `gitundo ${args.join(" ")} failed (${result.code})`,
        result.code,
        result.stderr,
      );
    }
    return result;
  }

  /** True when this folder is inside a git repository. */
  async inRepository(): Promise<boolean> {
    const res = await this.exec(["list", "--json"]);
    if (res.code !== 0) {
      // "not inside a git repository" exits 1 with a message on stderr
      return false;
    }
    return true;
  }

  async list(limit?: number, tagsOnly = false): Promise<Checkpoint[]> {
    const args = ["list", "--json"];
    if (limit !== undefined && limit > 0) {
      args.push("-n", String(limit));
    }
    if (tagsOnly) {
      args.push("--tags");
    }
    const res = await this.exec(args);
    if (res.code !== 0) {
      return [];
    }
    return parseJson<Checkpoint[]>(res.stdout) ?? [];
  }

  async status(): Promise<StatusInfo | null> {
    const res = await this.exec(["status", "--json"]);
    if (res.code !== 0) {
      return null;
    }
    return parseJson<StatusInfo>(res.stdout);
  }

  async snap(message?: string, tag?: string): Promise<Checkpoint> {
    const args = ["snap", "--json", "-f"];
    if (message) {
      args.push("-m", message);
    }
    if (tag) {
      args.push("-t", tag);
    }
    const res = await this.exec(args);
    if (res.code !== 0) {
      throw new CliError(res.stderr.trim() || "snapshot failed", res.code, res.stderr);
    }
    const parsed = parseJson<{ oid?: string }>(res.stdout);
    const oid = parsed?.oid ?? "";
    const list = await this.list(1);
    return list[0] ?? {
      id: oid,
      short: oid.slice(0, 7),
      tag: tag ?? "",
      message: message ?? "snapshot",
      when: new Date().toUTCString(),
      timestamp: Math.floor(Date.now() / 1000),
      snapshot_of: "",
    };
  }

  async restore(
    selector: string,
    opts: { hard?: boolean; index?: boolean; deleteExtraneous?: boolean } = {},
  ): Promise<string> {
    const args = ["restore"];
    if (opts.hard) {
      args.push("--hard");
    }
    if (opts.index) {
      args.push("--index");
    }
    if (opts.deleteExtraneous) {
      args.push("--delete-extraneous");
    }
    args.push(selector);
    const res = await this.exec(args);
    if (res.code !== 0) {
      throw new CliError(res.stderr.trim() || `restore failed for '${selector}'`, res.code, res.stderr);
    }
    return res.stdout.trim();
  }

  /** Full unified diff text that a checkpoint saved (stat + patch). */
  async diffSaved(selector: string): Promise<string> {
    const res = await this.exec(["diff", selector]);
    return res.stdout;
  }

  async tag(name: string, selector: string): Promise<void> {
    const res = await this.exec(["tag", name, selector]);
    if (res.code !== 0) {
      throw new CliError(res.stderr.trim() || "tag failed", res.code, res.stderr);
    }
  }

  async untag(name: string): Promise<void> {
    const res = await this.exec(["untag", name]);
    if (res.code !== 0) {
      throw new CliError(res.stderr.trim() || "untag failed", res.code, res.stderr);
    }
  }

  async prune(keep: number): Promise<string> {
    const res = await this.exec(["prune", "-k", String(keep)]);
    return res.stdout.trim();
  }

  async fileContentAt(selector: string, relPath: string): Promise<string | null> {
    // Use git directly for per-file reads; gitundo guarantees checkpoints are
    // ordinary commits, so this stays safe and fast.
    const { execFile } = await import("child_process");
    return new Promise((resolvePromise) => {
      execFile(
        "git",
        ["show", `${selector}:${relPath}`],
        { cwd: this.repoRoot, maxBuffer: 16 * 1024 * 1024, windowsHide: true },
        (err, stdout) => resolvePromise(err ? null : stdout),
      );
    });
  }
}
