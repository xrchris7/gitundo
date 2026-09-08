"""gitundo command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import __version__, core
from .core import (
    GitUndoError,
    NoCheckpoints,
    NotARepository,
    NothingToSnapshot,
)

PROG = "gitundo"


# --------------------------------------------------------------------------- #
# colour helpers (auto-disable when piped or NO_COLOR is set)
# --------------------------------------------------------------------------- #


def _colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COL = _colour()
_C = lambda code: f"\033[{code}m" if _COL else ""  # noqa: E731
RESET = _C("0")
BOLD = _C("1")
DIM = _C("2")
RED = _C("31")
GREEN = _C("32")
YELLOW = _C("33")
BLUE = _C("34")
MAGENTA = _C("35")
CYAN = _C("36")
GREY = _C("90")


def ok(msg: str) -> None:
    print(f"{GREEN}✔{RESET} {msg}")


def info(msg: str) -> None:
    print(msg)


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠{RESET} {msg}", file=sys.stderr)


def err(msg: str) -> None:
    print(f"{RED}✖{RESET} {msg}", file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    err(msg)
    sys.exit(code)


# --------------------------------------------------------------------------- #
# argument parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="The undo button git never had. "
        "Automatic safety-net snapshots for any git repository.",
        epilog="selectors:  latest (default) | N (snapshots ago, 0 = latest) "
        "| a tag name | an object-id prefix.  "
        "Run '%(prog)s help <command>' for details.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "-C",
        dest="chdir",
        metavar="DIR",
        default=None,
        help="run as if gitundo was started in DIR (like git -C)",
    )
    sub = p.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, help_: str, *, aliases: list[str] | None = None) -> argparse.ArgumentParser:
        return sub.add_parser(
            name, help=help_, aliases=aliases or [], description=help_, add_help=True
        )

    # snap ----------------------------------------------------------------- #
    sp = add(
        "snap",
        "Snapshot the current working state (staged + unstaged + untracked).",
        aliases=["checkpoint", "save", "s"],
    )
    sp.add_argument("message", nargs="?", default=None, help="label for this snapshot")
    sp.add_argument("-m", dest="message_opt", default=None, help="alias for MESSAGE")
    sp.add_argument("-t", "--tag", default=None, help="tag the snapshot (e.g. -t before-refactor)")
    sp.add_argument(
        "-f", "--force", action="store_true", help="create a snapshot even when nothing changed"
    )
    sp.add_argument(
        "--json", action="store_true", help="machine-readable JSON result (ok/created/oid/…)"
    )

    # list ---------------------------------------------------------------- #
    lp = add("list", "List checkpoints, newest first.", aliases=["ls", "log", "history"])
    lp.add_argument("-n", "--limit", type=int, default=None, help="show at most N checkpoints")
    lp.add_argument("--tags", action="store_true", help="show only tagged checkpoints")
    lp.add_argument(
        "--json",
        action="store_true",
        help="machine-readable JSON output (one array of checkpoint objects, newest first)",
    )

    # restore ------------------------------------------------------------- #
    rp = add("restore", "Restore your working tree to a checkpoint.", aliases=["rollback", "back"])
    rp.add_argument(
        "selector",
        nargs="?",
        default="latest",
        help="which checkpoint to restore (default: latest)",
    )
    rp.add_argument(
        "--index", action="store_true", help="also reset the index to match the checkpoint"
    )
    rp.add_argument(
        "--hard",
        action="store_true",
        help="overwrite local edits instead of keeping them aside as *.gitundo-keep",
    )
    rp.add_argument(
        "--delete-extraneous",
        action="store_true",
        help="also delete untracked files that did not exist in the checkpoint",
    )

    # diff ---------------------------------------------------------------- #
    dp = add(
        "diff", "Show what a checkpoint saved, or differences between checkpoints.", aliases=["d"]
    )
    dp.add_argument(
        "selector", nargs="?", default="latest", help="checkpoint to diff (default: latest)"
    )
    dp.add_argument(
        "--from",
        dest="from_sel",
        default=None,
        metavar="SEL",
        help="diff this checkpoint against another checkpoint SEL",
    )
    dp.add_argument(
        "--workdir",
        action="store_true",
        help="diff the checkpoint against the current working tree "
        "instead of the commit it was taken from",
    )

    # tag ----------------------------------------------------------------- #
    tp = add("tag", "Give a checkpoint a human-readable name.", aliases=["label", "name"])
    tp.add_argument("name", nargs="?", help="tag name (letters, digits, . _ -)")
    tp.add_argument(
        "selector", nargs="?", default="latest", help="checkpoint to tag (default: latest)"
    )

    ut = add("untag", "Remove a tag from a checkpoint.", aliases=["unlabel"])
    ut.add_argument(
        "name",
        nargs="?",
        default="latest",
        help="tag name, or a selector of the checkpoint to untag",
    )

    # prune --------------------------------------------------------------- #
    pp = add("prune", "Delete old checkpoints, keeping the newest N and tagged ones.")
    pp.add_argument(
        "-k",
        "--keep",
        type=int,
        default=100,
        metavar="N",
        help="keep the N most recent checkpoints (default: 100)",
    )
    pp.add_argument(
        "--no-tags", action="store_true", help="do not protect tagged checkpoints from pruning"
    )

    # status -------------------------------------------------------------- #
    add("status", "Show current protection state and latest checkpoints.", aliases=["st"]).add_argument(
        "--json", action="store_true", help="machine-readable JSON status"
    )

    # on / off ------------------------------------------------------------ #
    add("on", "Enable the guard for this repository (git config gitundo.enabled true)")
    add("off", "Disable the guard for this repository")

    # autowrap ------------------------------------------------------------ #
    aw = add(
        "autowrap",
        "Install/uninstall the automatic git wrapper for your shell.",
        aliases=["guard-install", "install"],
    )
    aw.add_argument("--uninstall", action="store_true", help="remove the wrapper")
    aw.add_argument(
        "--shell",
        default="bash",
        choices=["bash", "zsh"],
        help="which rc file to edit (default: bash)",
    )

    # internal ------------------------------------------------------------ #
    ig = add("_guard_git", "Internal: called by the auto-guard wrapper.", aliases=["guard-run"])
    ig.add_argument("git_args", nargs=argparse.REMAINDER, help="the original `git ...` arguments")

    return p


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #


def _row(cp: core.Checkpoint) -> str:
    tag = cp.tag or ""
    return (
        f"{CYAN}{cp.short()}{RESET}  {DIM}{cp.when}{RESET}  {MAGENTA}{tag:<16}{RESET}  {cp.subject}"
    )


def _files_badge(msg: str) -> str:
    short = msg.replace("\n", " ").strip()
    return short[:72] + ("…" if len(short) > 72 else "")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


def cmd_snap(a: argparse.Namespace) -> int:
    message = a.message_opt or a.message
    res: dict = {}
    try:
        res = core.snapshot(message=message, tag=a.tag, force=a.force)
    except NothingToSnapshot as exc:
        res = {"oid": "", "tag": a.tag or "", "empty": True, "created": False,
               "reason": str(exc), "staged": 0, "unstaged": 0, "untracked": 0}
    except GitUndoError as exc:
        if a.json:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 1
        die(str(exc))
    if a.json:
        print(json.dumps({
            "ok": True,
            "created": res.get("created", False),
            "oid": res.get("oid", ""),
            "short": (res.get("oid", "") or "")[:7],
            "tag": res.get("tag", ""),
            "staged": res.get("staged", 0),
            "unstaged": res.get("unstaged", 0),
            "untracked": res.get("untracked", 0),
            "reason": res.get("reason", ""),
        }))
        return 0
    if not res["created"]:
        info(f"{DIM}∅{RESET} nothing changed since the last snapshot ({res['oid'][:7]})")
        return 0
    tag = f" tagged {MAGENTA}{res['tag']}{RESET}" if res.get("tag") else ""
    bits = []
    if res.get("staged"):
        bits.append(f"{res['staged']} staged")
    if res.get("unstaged"):
        bits.append(f"{res['unstaged']} unstaged")
    if res.get("untracked"):
        bits.append(f"{res['untracked']} untracked")
    ok(f"checkpoint {BOLD}{res['oid'][:7]}{RESET}{tag} — " + (", ".join(bits) or "clean tree"))
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    cps = core.list_checkpoints(limit=a.limit, tags_only=a.tags)
    if a.json:
        print(json.dumps([_checkpoint_json(cp) for cp in cps], indent=2, default=str))
        return 0
    if not cps:
        info(
            f"{DIM}no checkpoints yet — run `gitundo snap` (or `gitundo help`) to create one.{RESET}"
        )
        return 0
    count, _, human = core.storage_stats()
    for cp in cps:
        print(_row(cp))
    print(f"{DIM}\n{len(cps)} shown · {count} total · ~{human} in .git objects{RESET}")
    return 0


def _checkpoint_json(cp: core.Checkpoint) -> dict:
    """Stable, documented JSON shape consumed by editors, CI and gitundo-vscode."""
    return {
        "id": cp.oid,
        "short": cp.short(),
        "tag": cp.tag or "",
        "message": cp.subject,
        "when": cp.when,
        "timestamp": cp.commit_time,
        "snapshot_of": cp.snapshot_of,
    }


def cmd_restore(a: argparse.Namespace) -> int:
    try:
        stats = core.restore(
            selector=a.selector, index=a.index, hard=a.hard, delete_extraneous=a.delete_extraneous
        )
    except GitUndoError as exc:
        die(str(exc))
    kept = stats.get("kept", 0)
    if kept:
        warn(
            f"{kept} file(s) with local edits were kept aside as "
            f"{DIM}*.gitundo-keep{RESET} (use {BOLD}--hard{RESET} to overwrite them)"
        )
    ok(
        f"restored working tree to {BOLD}{a.selector}{RESET} "
        f"({stats.get('restored', 0)} file(s) written, "
        f"{stats.get('removed', 0)} removed)"
    )
    print(
        f"  {DIM}committed history untouched; the current branch is exactly as you left it.{RESET}"
    )
    return 0


def cmd_diff(a: argparse.Namespace) -> int:
    try:
        if a.from_sel:
            out = core.diff_between(a=a.from_sel, b=a.selector)
        elif a.workdir:
            out = core.diff_workdir(selector=a.selector)
        else:
            out = core.diff_saved(selector=a.selector)
    except GitUndoError as exc:
        die(str(exc))
    if not out.strip():
        info(f"{DIM}(empty diff — that snapshot captured a clean tree){RESET}")
        return 0
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


def cmd_tag(a: argparse.Namespace) -> int:
    try:
        name = core.add_tag(name=a.name, selector=a.selector)
    except GitUndoError as exc:
        die(str(exc))
    ok(f"tagged checkpoint as {MAGENTA}{name}{RESET}")
    return 0


def cmd_untag(a: argparse.Namespace) -> int:
    try:
        core.remove_tag(name=a.name)
    except GitUndoError as exc:
        die(str(exc))
    ok(f"removed tag from checkpoint {a.name}")
    return 0


def cmd_prune(a: argparse.Namespace) -> int:
    try:
        removed = core.prune(keep=a.keep, protected_tags=not a.no_tags)
    except GitUndoError as exc:
        die(str(exc))
    ok(f"pruned {removed} old checkpoint(s)")
    return 0


def cmd_status(a: argparse.Namespace) -> int:
    repo = core.resolve_repo(".")
    try:
        cps = core.list_checkpoints(limit=5)
    except GitUndoError:
        cps = []
    if getattr(a, "json", False):
        print(
            json.dumps(
                {
                    "version": __version__,
                    "enabled": core.is_enabled(repo),
                    "autowrapped": core.is_autowrapped(),
                    "head": core.head_oid(repo) or "",
                    "count": len(core.read_checkpoints(repo)),
                    "recent": [_checkpoint_json(c) for c in cps],
                },
                indent=2,
                default=str,
            )
        )
        return 0
    state = []
    if core.is_enabled(repo):
        state.append(f"{GREEN}guard: on{RESET}")
    else:
        state.append(f"{GREY}guard: off{RESET} (run `gitundo on`)")
    if core.is_autowrapped():
        state.append(f"{GREEN}auto-wrap: on{RESET}")
    else:
        state.append(f"{GREY}auto-wrap: off{RESET} (run `gitundo autowrap`)")
    print(" · ".join(state))
    head = core.head_oid(repo)
    print(f"branch head: {head[:7] if head else DIM + '(unborn)' + RESET}")
    cps = core.list_checkpoints(limit=5)
    if cps:
        print(f"\n{BOLD}latest checkpoints{RESET}")
        for cp in cps:
            print("  " + _row(cp))
    else:
        print(f"\n{DIM}no checkpoints yet.{RESET}")
    count, obj, human = core.storage_stats()
    print(f"{DIM}{count} checkpoint(s) · ~{human} stored in .git{RESET}")
    return 0


def cmd_on(a: argparse.Namespace) -> int:
    core.set_enabled(True)
    ok("guard enabled for this repository (git config gitundo.enabled true)")
    return 0


def cmd_off(a: argparse.Namespace) -> int:
    core.set_enabled(False)
    ok("guard disabled for this repository")
    return 0


def cmd_autowrap(a: argparse.Namespace) -> int:
    try:
        if a.uninstall:
            rc = core.uninstall_autowrap(a.shell)
            ok(f"removed the auto-guard from ~/{rc.name}")
        else:
            rc = core.install_autowrap(a.shell)
            ok(f"auto-guard installed in ~/{rc.name} — open a new shell to activate")
    except GitUndoError as exc:
        die(str(exc))
    print(
        f"\n{DIM}Destructive git commands (reset --hard, clean -dfx, rebase …) will now\n"
        f"snapshot your state automatically first. Disable any time with:\n"
        f"    export GITUNDO_DISABLE=1{RESET}"
    )
    return 0


def cmd_guard_git(a: argparse.Namespace) -> int:
    """Invoked by the auto-wrap ``git()`` function. Snapshots before clearly
    destructive git invocations, then runs the real git command."""
    args = a.git_args or []
    if os.environ.get("GITUNDO_DISABLE"):
        return _exec_git(args)
    line = "git " + " ".join(args)
    danger = core.describe_danger(line)
    if danger and core.is_repository("."):
        try:
            res = core.snapshot()
            if res.get("created"):
                print(
                    f"{GREEN}gitundo{RESET} snapshot before {danger} → {res['oid'][:7]}",
                    file=sys.stderr,
                )
        except GitUndoError:
            pass  # never block the user's git command
    return _exec_git(args)


def _exec_git(args: list[str]) -> int:
    """Run the real git binary, inheriting stdio and exit status."""
    try:
        code = subprocess.call(["git", *args])
    except FileNotFoundError:
        die("could not find the real `git` binary", 127)
    except KeyboardInterrupt:
        return 130
    return code if code is not None else 1


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

_COMMANDS = {
    "snap": cmd_snap,
    "checkpoint": cmd_snap,
    "save": cmd_snap,
    "s": cmd_snap,
    "list": cmd_list,
    "ls": cmd_list,
    "log": cmd_list,
    "history": cmd_list,
    "restore": cmd_restore,
    "rollback": cmd_restore,
    "back": cmd_restore,
    "diff": cmd_diff,
    "d": cmd_diff,
    "tag": cmd_tag,
    "label": cmd_tag,
    "name": cmd_tag,
    "untag": cmd_untag,
    "unlabel": cmd_untag,
    "prune": cmd_prune,
    "status": cmd_status,
    "st": cmd_status,
    "on": cmd_on,
    "off": cmd_off,
    "autowrap": cmd_autowrap,
    "guard-install": cmd_autowrap,
    "install": cmd_autowrap,
    "_guard_git": cmd_guard_git,
    "guard-run": cmd_guard_git,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if argv and argv[0] in ("help", "--help", "-h"):
        if len(argv) == 1:
            parser.print_help()
            return 0
        # print help of the subcommand
        subargv = [argv[1], "--help"]
        subargv[0] = argv[1]
        try:
            ns = parser.parse_args(subargv)
            if ns.command and ns.command in _COMMANDS:
                return 0
        except SystemExit:
            return 0
        return 0

    try:
        a = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    if not a.command:
        parser.print_help()
        return 0

    # honor -C by chdir-ing before anything else
    if getattr(a, "chdir", None):
        try:
            os.chdir(a.chdir)
        except OSError as exc:
            die(f"cannot enter '{a.chdir}': {exc}", 2)

    handler = _COMMANDS.get(a.command)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(a) or 0
    except NotARepository as exc:
        die(str(exc))
    except NoCheckpoints as exc:
        die(str(exc))
    except GitUndoError as exc:
        die(str(exc))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
