"""Core engine for gitundo.

Everything here is a plain function of a repository on disk and is deliberately
UI-free so it can be reused by the CLI, the shell guard, and the test-suite.

Mental model
------------
* A **checkpoint** is an ordinary git commit that stores a complete snapshot of
  your working state: every tracked file as it is on disk right now, plus every
  untracked (non-ignored) file. It is stored on a hidden ref,
  ``refs/gitundo/checkpoints``, so git itself does the deduplication, and it
  never touches your branches, index, tags or history.
* Checkpoints are useful *because* git normally only protects committed work.
  If you blast away uncommitted changes with ``reset --hard`` / ``clean -fdx``
  / a bad rebase, gitundo can bring them back.
* ``restore`` writes checkpoint files back into the working tree only. Committed
  history is never rewritten or deleted, and local edits are never silently
  overwritten (they are parked as ``<file>.gitundo-keep`` unless ``--hard``).

Every checkpoint commit is authored by ``gitundo`` (timestamp ``@0``) so it is
instantly recognisable and never impersonates you. Its message carries
structured ``key: value`` metadata lines::

    snapshot-of: <oid>      # HEAD at capture time
    gitundo-tag: <name>     # optional human tag
    created-by: gitundo
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import CHECKPOINT_REF, SNAPSHOT_AUTHOR, SNAPSHOT_EMAIL

GIT = shutil.which("git") or "git"

# Well-known SHA-1 of git's empty tree object (always usable in diffs).
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

_MAX_BLOB_COMPARE = 64 * 1024 * 1024  # don't byte-compare files above this size


# --------------------------------------------------------------------------- #
# exceptions
# --------------------------------------------------------------------------- #


class GitUndoError(Exception):
    """Base error; str(e) is user-presentable."""


class NotARepository(GitUndoError):
    pass


class NoCheckpoints(GitUndoError):
    pass


class NothingToSnapshot(GitUndoError):
    pass


# --------------------------------------------------------------------------- #
# process plumbing
# --------------------------------------------------------------------------- #


def _run(
    args: list[str],
    repo: Path,
    *,
    check: bool = True,
    text: bool = True,
    input_bytes: Optional[bytes] = None,
    env_extra: Optional[dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Run git inside *repo* with the environment scrubbed of anything that
    could redirect git into a *different* repository (GIT_DIR & friends)."""
    env = os.environ.copy()
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
        "GIT_CEILING_DIRECTORIES",
    ):
        env.pop(key, None)
    if env_extra:
        env.update(env_extra)
    # Providing bytes on stdin requires binary pipes regardless of `text`.
    if input_bytes is not None:
        text = False
    return subprocess.run(
        [GIT, *args],
        cwd=str(repo),
        env=env,
        text=text,
        input=input_bytes,
        capture_output=True,
        check=check,
    )


def _out(args: list[str], repo: Path, *, check: bool = True, env_extra=None) -> str:
    return _run(args, repo=repo, check=check, env_extra=env_extra).stdout


def _bytes(args: list[str], repo: Path, *, check: bool = True, input_bytes=None) -> bytes:
    return _run(args, repo=repo, check=check, input_bytes=input_bytes, text=False).stdout


def _zsplit(raw: str) -> list[str]:
    return [p for p in raw.split("\x00") if p]


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #


def resolve_repo(path: Path | str = ".") -> Path:
    """Absolute path of the repository root containing *path* (or raise)."""
    p = Path(path or os.getcwd()).resolve()
    try:
        proc = _run(["rev-parse", "--show-toplevel"], repo=p, check=False)
    except OSError:  # path does not exist
        raise NotARepository(
            f"'{p}' does not exist\n(run `gitundo` inside a git repository)"
        ) from None
    if proc.returncode != 0:
        raise NotARepository(
            f"'{p}' is not inside a git repository\n"
            "(run `git init` first, or point gitundo at a repo)"
        )
    return Path(proc.stdout.strip())


def is_repository(path: Path | str = ".") -> bool:
    try:
        resolve_repo(path)
        return True
    except GitUndoError:
        return False


def head_oid(repo: Path) -> str:
    return _out(["rev-parse", "--verify", "-q", "HEAD"], repo, check=False).strip()


def empty_tree_oid(repo: Path) -> str:
    """An empty tree object that is guaranteed to exist in this repository."""
    if _run(["cat-file", "-e", EMPTY_TREE], repo, check=False).returncode == 0:
        return EMPTY_TREE
    made = _out(["mktree"], repo, check=False).strip()
    return made or EMPTY_TREE


# --------------------------------------------------------------------------- #
# checkpoint model
# --------------------------------------------------------------------------- #


@dataclass
class Checkpoint:
    oid: str
    subject: str
    body: str
    author_name: str
    author_email: str
    commit_time: int
    snapshot_of: str = ""
    tag: str = ""

    @property
    def when(self) -> str:
        return datetime.fromtimestamp(self.commit_time, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

    def short(self) -> str:
        return self.oid[:7]

    def describe(self) -> str:
        if self.tag:
            return f"{self.tag} ({self.short()})"
        return self.short()


def _parse_meta(body: str) -> tuple[str, str]:
    tag, snap = "", ""
    for line in body.splitlines():
        if line.startswith("gitundo-tag:"):
            tag = line.split(":", 1)[1].strip()
        elif line.startswith("snapshot-of:"):
            snap = line.split(":", 1)[1].strip()
    return tag, snap


def read_checkpoints(repo: Path) -> list[Checkpoint]:
    """All checkpoints reachable from the checkpoint ref, oldest → newest.

    The ref always points at the newest checkpoint and checkpoints form a
    linear chain (each one's parent is the previous checkpoint), so ``git log
    --reverse`` gives the authoritative chronological order -- which matters
    because several snapshots taken within the same second share a timestamp.
    """
    proc = _run(
        ["log", "--reverse", "--format=%H%x1f%an%x1f%ae%x1f%ct%x1f%B%x1e", CHECKPOINT_REF],
        repo=repo,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    out: list[Checkpoint] = []
    for record in proc.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record.strip():
            continue
        fields = record.split("\x1f")
        if len(fields) < 5:
            continue
        oid, author, email, ct, body = fields[:5]
        body = body.strip()
        tag, snap = _parse_meta(body)
        out.append(
            Checkpoint(
                oid=oid,
                subject=body.splitlines()[0].strip() if body else "(no message)",
                body=body,
                author_name=author,
                author_email=email,
                commit_time=int(ct or 0),
                snapshot_of=snap,
                tag=tag,
            )
        )
    _by_oid = _tags_by_oid(repo)
    for cp in out:
        cp.tag = cp.tag or _by_oid.get(cp.oid, "")
    return out


def _to_int(s: str) -> Optional[int]:
    try:
        return int(s)
    except ValueError:
        return None


def find_checkpoint(
    repo: Path, selector: Optional[str], cps: Optional[list[Checkpoint]] = None
) -> Optional[Checkpoint]:
    """Resolve a selector: ``latest`` (default), an int ``N`` = "N snapshots
    ago" (0 = latest), a tag name, or an object-id prefix.

    Numeric selectors only mean "N snapshots ago" when N is within range; an
    out-of-range integer (e.g. an all-digit object-id prefix) falls through to
    tag / id-prefix matching.
    """
    cps = read_checkpoints(repo) if cps is None else cps
    if not cps:
        return None
    sel = (selector or "latest").strip().lower()
    if sel in ("latest", "last", "head", "@", "0"):
        return cps[-1]
    n = _to_int(sel)
    if n is not None and 0 < n <= len(cps):
        return cps[-(n + 1)]
    for c in reversed(cps):
        if c.tag and c.tag.lower() == sel:
            return c
    for c in reversed(cps):
        if c.oid.startswith(sel) or c.short().startswith(sel):
            return c
    return None


def _need(
    repo: Path, selector: Optional[str], cps: Optional[list[Checkpoint]] = None
) -> Checkpoint:
    cp = find_checkpoint(repo, selector, cps)
    if cp is None:
        raise NoCheckpoints(
            f"no checkpoint matches '{selector}'"
            if selector
            else "no checkpoints yet — run `gitundo snap` (or `gitundo help`)"
        )
    return cp


# --------------------------------------------------------------------------- #
# snapshot
# --------------------------------------------------------------------------- #


def _state_lists(repo: Path) -> tuple[list[str], list[str], list[str]]:
    staged = _zsplit(_out(["diff", "--cached", "--name-only", "-z"], repo, check=False))
    unstaged = _zsplit(_out(["diff", "--name-only", "-z"], repo, check=False))
    untracked = _zsplit(
        _out(["ls-files", "--others", "--exclude-standard", "-z"], repo, check=False)
    )
    return staged, unstaged, untracked


def _build_tree(
    repo: Path,
    staged: list[str] | None = None,
    unstaged: list[str] | None = None,
    untracked: list[str] | None = None,
) -> str:
    """Tree object representing *everything on disk right now* (tracked files as
    they exist, staged or not, plus untracked-but-not-ignored files), built on a
    throwaway index that never touches the real one."""
    if staged is None or unstaged is None or untracked is None:
        staged, unstaged, untracked = _state_lists(repo)
    touched = sorted(set(staged) | set(unstaged) | set(untracked))
    tmp = repo / f".gitundo-tmp-index-{os.getpid()}"
    env = {"GIT_INDEX_FILE": str(tmp)}
    try:
        head = head_oid(repo)
        if head:
            _out(["read-tree", head], repo, env_extra=env)
        else:
            _out(["read-tree", empty_tree_oid(repo)], repo, env_extra=env)
        if touched:
            # present files are added (content read from disk), deleted files
            # are removed -- exactly the state of the working directory.
            payload = b"".join(p.encode("utf-8", "surrogateescape") + b"\0" for p in touched)
            _run(
                ["update-index", "-z", "--add", "--remove", "--stdin"],
                repo,
                env_extra=env,
                input_bytes=payload,
                check=False,
            )
        return _out(["write-tree"], repo, env_extra=env).strip()
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _message(message: Optional[str], repo: Path) -> str:
    head = head_oid(repo)
    lines = [(message or "checkpoint").replace("\n", " ").strip() or "checkpoint"]
    lines.append(f"snapshot-of: {head}" if head else "snapshot-of: (unborn)")
    lines.append(f"created-by: {SNAPSHOT_AUTHOR}")
    return "\n".join(lines)


def _snapshot_env() -> dict[str, str]:
    """Checkpoint commits are authored by *gitundo*, never the user, so they are
    instantly recognisable in `git log` and can never be mistaken for (or
    signed as) the user's own work. Timestamps stay real for useful history."""
    return {
        "GIT_AUTHOR_NAME": SNAPSHOT_AUTHOR,
        "GIT_AUTHOR_EMAIL": SNAPSHOT_EMAIL,
        "GIT_COMMITTER_NAME": SNAPSHOT_AUTHOR,
        "GIT_COMMITTER_EMAIL": SNAPSHOT_EMAIL,
    }


def snapshot(
    path: Path | str = ".",
    message: Optional[str] = None,
    tag: Optional[str] = None,
    *,
    force: bool = False,
) -> dict:
    """Store the current working state as a checkpoint on the hidden ref.

    Returns ``{"oid", "tag", "empty", "created", "staged", "unstaged",
    "untracked", "total"}``. ``empty=True`` and ``created=False`` when there was
    nothing new to capture (unless --force).
    """
    repo = resolve_repo(path)
    staged, unstaged, untracked = _state_lists(repo)
    cps = read_checkpoints(repo)
    last = cps[-1] if cps else None

    counts = {
        "staged": len(staged),
        "unstaged": len(unstaged),
        "untracked": len(untracked),
        "total": len(set(staged) | set(unstaged) | set(untracked)),
    }

    tree = _build_tree(repo, staged, unstaged, untracked)
    if not force and last is not None:
        last_tree = _out(["rev-parse", f"{last.oid}^{{tree}}"], repo, check=False).strip()
        if tree == last_tree:
            if tag and last is not None:
                try:
                    _tag_ref_commit(repo, tag, last.oid)
                except GitUndoError:
                    pass  # duplicate tag on an empty snapshot: not an error
            return {"oid": last.oid, "tag": tag or "", "empty": True, "created": False, **counts}
    if not force and last is None and tree == empty_tree_oid(repo):
        raise NothingToSnapshot("nothing to snapshot (empty repository)")

    parent = last.oid if last else None
    cmd = ["commit-tree", tree, "-m", _message(message, repo)]
    if parent:
        cmd += ["-p", parent]
    oid = _out(cmd, repo, env_extra=_snapshot_env()).strip()
    if not oid:
        raise GitUndoError("git failed to create the checkpoint object")
    _out(["update-ref", "-m", f"gitundo: snapshot {oid[:7]}", CHECKPOINT_REF, oid], repo)
    if tag:
        _tag_ref_commit(repo, tag, oid)
    return {"oid": oid, "tag": tag or "", "empty": False, "created": True, **counts}


# --------------------------------------------------------------------------- #
# listing
# --------------------------------------------------------------------------- #


def list_checkpoints(
    path: Path | str = ".", *, limit: Optional[int] = None, tags_only: bool = False
) -> list[Checkpoint]:
    repo = resolve_repo(path)
    cps = read_checkpoints(repo)
    if tags_only:
        cps = [c for c in cps if c.tag]
    cps.reverse()
    if limit and limit > 0:
        cps = cps[:limit]
    return cps


def storage_stats(path: Path | str = ".") -> tuple[int, int, str]:
    """(checkpoint_count, object_bytes, human_bytes) for this repo."""
    repo = resolve_repo(path)
    cps = read_checkpoints(repo)
    obj = 0
    proc = _run(["count-objects", "-v"], repo, check=False)
    if proc.returncode == 0:
        m = re.search(r"size: (\d+)", proc.stdout)
        if m:
            obj = int(m.group(1)) * 1024
    return len(cps), obj, _human(obj)


def _human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} TiB"


# --------------------------------------------------------------------------- #
# tags
# --------------------------------------------------------------------------- #
# Tags are lightweight refs under ``refs/gitundo/tags/<name>`` pointing at a
# checkpoint commit. Unlike rewriting commit messages (which would corrupt the
# checkpoint chain), a ref can tag *any* checkpoint -- old or new -- with zero
# history surgery, and `git tag` output is never polluted.

TAG_REF_PREFIX = "refs/gitundo/tags/"

_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _tag_ref_commit(repo: Path, name: str, oid: str) -> None:
    """Point (or move) a tag ref at a checkpoint, validating the name."""
    if not name or not _TAG_RE.match(name) or name.endswith("."):
        raise GitUndoError(
            "tag must be 1-64 characters: letters, digits and '.', '_', '-' "
            "(start with a letter/digit, must not end with '.')"
        )
    ref = TAG_REF_PREFIX + name
    _out(["update-ref", "-m", f"gitundo: tag {name}", ref, oid], repo)


def add_tag(
    path: Path | str = ".", name: Optional[str] = None, selector: Optional[str] = None
) -> str:
    """Give a checkpoint a human-readable name."""
    repo = resolve_repo(path)
    cps = read_checkpoints(repo)
    if not cps:
        raise NoCheckpoints("no checkpoints yet — run `gitundo snap` first")
    if not name or not _TAG_RE.match(name) or name.endswith("."):
        raise GitUndoError(
            "tag must be 1-64 characters: letters, digits and '.', '_', '-' "
            "(start with a letter/digit, must not end with '.')"
        )
    if (
        _run(["show-ref", "--verify", "-q", TAG_REF_PREFIX + name], repo, check=False).returncode
        == 0
    ):
        raise GitUndoError(f"tag '{name}' already exists")
    cp = _need(repo, selector, cps)
    _tag_ref_commit(repo, name, cp.oid)
    return name


def remove_tag(path: Path | str = ".", name: Optional[str] = None) -> None:
    """Remove a tag. Accepts the tag name or a checkpoint selector."""
    repo = resolve_repo(path)
    if (
        name
        and not _run(
            ["show-ref", "--verify", "-q", TAG_REF_PREFIX + name], repo, check=False
        ).returncode
    ):
        _out(["update-ref", "-d", "-m", f"gitundo: untag {name}", TAG_REF_PREFIX + name], repo)
        return
    # selector form: resolve checkpoint, remove any of its tags
    cp = _need(repo, name or "latest", read_checkpoints(repo))
    removed = False
    for tag, oid in _tag_map(repo).items():
        if oid == cp.oid:
            _out(["update-ref", "-d", "-m", f"gitundo: untag {tag}", TAG_REF_PREFIX + tag], repo)
            removed = True
    if not removed:
        raise GitUndoError(f"no tag found on checkpoint '{name or 'latest'}'")


def _tag_map(repo: Path) -> dict[str, str]:
    """tag name -> checkpoint oid."""
    raw = _out(
        ["for-each-ref", "--format=%(refname)%00%(objectname)", TAG_REF_PREFIX], repo, check=False
    )
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if not line:
            continue
        ref, _, oid = line.partition("\x00")
        tag = ref[len(TAG_REF_PREFIX) :] if ref.startswith(TAG_REF_PREFIX) else ref
        if oid:
            out[tag] = oid
    return out


def _tags_by_oid(repo: Path) -> dict[str, str]:
    """checkpoint oid -> tag name (first tag wins for display)."""
    by: dict[str, str] = {}
    for tag, oid in _tag_map(repo).items():
        by.setdefault(oid, tag)
    return by


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #


def _base_for(repo: Path, cp: Checkpoint) -> str:
    base = cp.snapshot_of
    if not base or base == "(unborn)":
        return empty_tree_oid(repo)
    return base


def diff_saved(path: Path | str = ".", selector: Optional[str] = None) -> str:
    """What a checkpoint captured: its tree vs the HEAD that was checked out at
    capture time (empty when the snapshot was taken on a clean tree)."""
    repo = resolve_repo(path)
    cp = _need(repo, selector, read_checkpoints(repo))
    base = _base_for(repo, cp)
    stat = _out(["diff", "--stat", base, cp.oid], repo, check=False).rstrip()
    patch = _out(["diff", base, cp.oid], repo, check=False).rstrip()
    if stat and patch:
        return stat + "\n\n" + patch + "\n"
    return (stat + "\n") if stat else (patch + "\n" if patch else "")


def diff_between(path: Path | str = ".", a: Optional[str] = "1", b: Optional[str] = "0") -> str:
    repo = resolve_repo(path)
    cps = read_checkpoints(repo)
    ca, cb = _need(repo, a, cps), _need(repo, b, cps)
    return _out(["diff", ca.oid, cb.oid], repo, check=False)


def diff_workdir(path: Path | str = ".", selector: Optional[str] = None) -> str:
    """Checkpoint vs. the current working tree (what `restore` would change)."""
    repo = resolve_repo(path)
    cp = _need(repo, selector, read_checkpoints(repo))
    head = head_oid(repo) or _base_for(repo, cp)
    return _out(["diff", cp.oid, head], repo, check=False)


# --------------------------------------------------------------------------- #
# restore
# --------------------------------------------------------------------------- #


def restore(
    path: Path | str = ".",
    selector: Optional[str] = None,
    *,
    index: bool = False,
    hard: bool = False,
    delete_extraneous: bool = False,
) -> dict[str, int]:
    """Restore the working tree to a checkpoint.

    Safety guarantees (documented and enforced):
    * committed history / branches / tags / HEAD are never modified;
    * files with local edits are parked as ``<path>.gitundo-keep`` and reported
      (unless ``--hard``, which overwrites them);
    * files that exist only in commits newer than the checkpoint are never
      deleted (they are safe in git already);
    * untracked files are never deleted unless ``--delete-extraneous``.

    Returns counts: ``{"restored", "kept", "removed"}``.
    """
    repo = resolve_repo(path)
    cp = _need(repo, selector, read_checkpoints(repo))
    return _restore(repo, cp, index=index, hard=hard, delete_extraneous=delete_extraneous)


def _tree_map(repo: Path, treeish: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, oid) for every entry under *treeish*."""
    raw = _out(["ls-tree", "-r", "-z", treeish], repo, check=False)
    out: dict[str, tuple[str, str]] = {}
    for rec in raw.split("\x00"):
        if not rec:
            continue
        meta, _, path = rec.partition("\t")
        if not path:
            continue
        parts = meta.split(" ")
        if len(parts) >= 3:
            out[path] = (parts[0], parts[2])
    return out


def _disk_oid(repo: Path, rel: str) -> Optional[str]:
    """Object id of a path's current on-disk content (None if missing/dir)."""
    p = repo / rel
    try:
        if p.is_symlink():
            target = os.readlink(p).encode("utf-8")
            return _hash_bytes(repo, target)
        if p.is_file():
            return _out(["hash-object", "--", rel], repo, check=False).strip() or None
    except OSError:
        return None
    return None


def _hash_bytes(repo: Path, data: bytes) -> Optional[str]:
    proc = _run(
        ["hash-object", "-t", "blob", "--stdin"], repo, text=False, input_bytes=data, check=False
    )
    return proc.stdout.decode().strip() or None


def _restore(
    repo: Path, cp: Checkpoint, *, index: bool, hard: bool, delete_extraneous: bool
) -> dict[str, int]:
    stats = {"restored": 0, "kept": 0, "removed": 0}
    cp_map = _tree_map(repo, cp.oid)
    base = cp.snapshot_of
    base_map: dict[str, tuple[str, str]] = {}
    if base and base != "(unborn)":
        try:
            base_map = _tree_map(repo, base)
        except GitUndoError:
            base_map = {}

    # 1. write/refresh every file the checkpoint contains -------------------
    for rel, (mode, oid) in sorted(cp_map.items()):
        if mode.startswith("16"):  # submodule gitlink — requires a checkout
            continue
        dest = repo / rel
        local = _disk_oid(repo, rel)
        if local == oid:
            continue  # already exact
        base_oid = base_map.get(rel, (None, None))[1]
        unchanged_since_capture = base_oid is not None and local == base_oid
        if local is not None and not unchanged_since_capture and not hard:
            _keep_aside(repo, rel)
            stats["kept"] += 1
        try:
            if dest.is_dir() and not dest.is_symlink():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            _materialize(repo, oid, mode, dest)
            stats["restored"] += 1
        except OSError as exc:  # pragma: no cover (fs-dependent)
            raise GitUndoError(f"could not restore '{rel}': {exc}") from exc

    # 2. optional index reset -----------------------------------------------
    if index:
        _out(["read-tree", cp.oid], repo)

    # 3. optional cleanup of untracked debris -------------------------------
    if delete_extraneous:
        untracked = set(
            _zsplit(_out(["ls-files", "--others", "--exclude-standard", "-z"], repo, check=False))
        )
        for rel in sorted(untracked - set(cp_map)):
            p = repo / rel
            if p.is_file() or p.is_symlink():
                try:
                    p.unlink()
                    stats["removed"] += 1
                except OSError:
                    pass
    return stats


def _materialize(repo: Path, oid: str, mode: str, dest: Path) -> None:
    if mode.startswith("12"):
        target = _bytes(["cat-file", "blob", oid], repo).decode("utf-8", "replace")
        os.symlink(target, dest)
    else:
        dest.write_bytes(_bytes(["cat-file", "blob", oid], repo))


def _keep_aside(repo: Path, rel: str) -> None:
    src = repo / rel
    if not src.exists():
        return
    n = 0
    while True:
        name = f"{rel}.gitundo-keep" if n == 0 else f"{rel}.gitundo-keep.{n}"
        target = repo / name
        if not target.exists():
            src.replace(target)
            return
        n += 1


# --------------------------------------------------------------------------- #
# prune
# --------------------------------------------------------------------------- #


def prune(path: Path | str = ".", keep: int = 100, *, protected_tags: bool = True) -> int:
    """Drop old checkpoints, keeping the newest *keep* plus tagged ones. The
    survivor chain is rewritten linearly; dropped commits become unreachable
    (reclaimed by a later ``git gc``). Returns how many were removed."""
    repo = resolve_repo(path)
    cps = read_checkpoints(repo)
    if not cps:
        raise NoCheckpoints("no checkpoints to prune")
    by_time = sorted(cps, key=lambda c: c.commit_time)
    tagged_oids = {oid for tag, oid in _tag_map(repo).items()} if protected_tags else set()
    protected: set[str] = set()
    if protected_tags:
        protected |= tagged_oids
    if keep > 0:
        protected |= {c.oid for c in by_time[-keep:]}
    doomed = [c for c in by_time if c.oid not in protected]
    if not doomed:
        return 0
    survivors = [c for c in by_time if c.oid in protected]
    if not survivors:
        raise GitUndoError("refusing to prune every checkpoint")
    new_oid: Optional[str] = None
    renamed: dict[str, str] = {}
    for c in survivors:
        tree = _out(["rev-parse", f"{c.oid}^{{tree}}"], repo).strip()
        cmd = ["commit-tree", tree, "-m", c.body or c.subject]
        if new_oid:
            cmd += ["-p", new_oid]
        renamed[c.oid] = _out(cmd, repo, env_extra=_snapshot_env()).strip()
        new_oid = renamed[c.oid]
    _out(
        [
            "update-ref",
            "-m",
            f"gitundo: prune {len(doomed)} checkpoint(s)",
            CHECKPOINT_REF,
            new_oid,
            by_time[-1].oid,
        ],
        repo,
    )
    # surviving checkpoints were rewritten (new oids): re-point any tags
    for tag, oid in _tag_map(repo).items():
        if oid in renamed:
            _out(
                [
                    "update-ref",
                    "-m",
                    f"gitundo: retag {tag} after prune",
                    TAG_REF_PREFIX + tag,
                    renamed[oid],
                    oid,
                ],
                repo,
            )
    return len(doomed)


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #


def set_enabled(path: Path | str = ".", enabled: bool = True) -> None:
    repo = resolve_repo(path)
    if enabled:
        _run(["config", "gitundo.enabled", "true"], repo)
    else:
        _run(["config", "--unset-all", "gitundo.enabled"], repo, check=False)


def is_enabled(path: Path | str = ".") -> bool:
    try:
        repo = resolve_repo(path)
    except GitUndoError:
        return False
    val = _out(["config", "--get", "gitundo.enabled"], repo, check=False).strip().lower()
    return val in ("true", "1", "yes", "on")


# --------------------------------------------------------------------------- #
# destructive-command detection (used by the guard)
# --------------------------------------------------------------------------- #

DESTRUCTIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    # -- general shell file-destroyers (checked before git, so that `rm -rf`
    #    is never mislabelled as a git command) ------------------------------
    (r"(?:^|&&|\||;)\s*\brm\s+(?:-[a-zA-Z]*[rf][a-zA-Z]*)", "rm -r/-f"),
    (r"(?:^|&&|\||;)\s*\brmdir\s+", "rmdir"),
    (r"(?:^|&&|\||;)\s*\bshred\s+", "shred"),
    (r"(?:^|&&|\||;)\s*\b(?:mv|cp)\s+", "mv / cp"),
    (r"(?:^|&&|\||;)\s*\b(?:truncate|dd)\s+", "truncate / dd"),
    (r"(?:^|&&|\||;)\s*(?:sed|perl|python|python3|awk|ruby)\b[^|;&]*\s+-i\b", "in-place text edit"),
    # -- git commands that destroy uncommitted work -------------------------
    # (history-only operations such as merge/rebase/revert/cherry-pick are
    #  deliberately NOT guarded: git's reflog already protects them and they
    #  never delete uncommitted changes, so auto-snapshots would only add noise)
    (r"(?:^|&&|\||;)\s*git\s+reset\s+(?:-[a-zA-Z]*\s+)*--hard\b", "git reset --hard"),
    (r"(?:^|&&|\||;)\s*git\s+clean\s+(?:-[a-zA-Z]*[dfx][a-zA-Z]*)", "git clean -dfx"),
    (r"(?:^|&&|\||;)\s*git\s+checkout\s+(?:-[a-zA-Z]*f|--force)\b", "git checkout --force"),
    (r"(?:^|&&|\||;)\s*git\s+checkout\s+--(?=\s|$)", "git checkout -- (discard)"),
    (r"(?:^|&&|\||;)\s*git\s+checkout\s+\.\s*$", "git checkout . (discard)"),
    (r"(?:^|&&|\||;)\s*git\s+checkout\s+[^\s]+\s+--(?=\s|$)", "git checkout <ref> -- <path>"),
    (r"(?:^|&&|\||;)\s*git\s+restore\b", "git restore"),
    (r"(?:^|&&|\||;)\s*git\s+rm\b", "git rm"),
    (r"(?:^|&&|\||;)\s*git\s+branch\s+(?:-[a-zA-Z]*D\b)", "git branch -D"),
    (r"(?:^|&&|\||;)\s*git\s+update-ref\b", "git update-ref"),
    (r"(?:^|&&|\||;)\s*git\s+replace\b", "git replace"),
)


def describe_danger(command: str) -> Optional[str]:
    """Human label when *command* clearly destroys state, else None.

    Conservative on purpose: only explicit destructive flags trip it, so normal
    git usage is never interrupted.
    """
    cmd = command.strip()
    if not cmd or cmd.startswith("#") or len(cmd) > 4096:
        return None
    for pattern, label in DESTRUCTIVE_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return label
    return None


# --------------------------------------------------------------------------- #
# shell auto-guard
# --------------------------------------------------------------------------- #

GUARD_MARKER = "# >>> gitundo auto-guard (managed by `gitundo autowrap`) <<<"
_RC_FILES = {"bash": ".bashrc", "zsh": ".zshrc"}


def autowrap_block(shell: str = "bash") -> str:
    """Shell source block defining a real ``git()`` function.

    A function (not an alias) works in scripts too. It runs a cheap string
    check first: only commands that *look* destructive are handed to gitundo's
    detector (which snapshots when appropriate); everything else runs through
    to the real git immediately, so ordinary commands pay no measurable cost.
    """
    del shell  # identical block for bash and zsh today
    return "".join(
        [
            GUARD_MARKER + "\n",
            "# gitundo auto-guard: snapshot before destructive git commands.\n",
            "# Disable any time with:  export GITUNDO_DISABLE=1\n",
            "git() {\n",
            '  if [ -n "${GITUNDO_DISABLE:-}" ]; then\n',
            '    command git "$@"; return $?\n',
            "  fi\n",
            # cheap pre-filter: suspicious flags go to the real detector
            '  case " $*" in\n',
            '    *" --hard"*|*"clean"*|*"--force"*|*" -f"*|*" restore"*|*"branch"*|\\\n',
            '    *" rm"*|*"update-ref"*|*"replace"*|*"rebase"*|*"revert"*|*"cherry-pick"*) : ;;\n',
            '    *) command git "$@"; return $? ;;\n',
            "  esac\n",
            '  command gitundo _guard_git "$@"\n',
            "}\n",
            GUARD_MARKER + "\n",
        ]
    )


def is_autowrapped(shell: str = "bash") -> bool:
    rc = Path.home() / _RC_FILES.get(shell, ".bashrc")
    return rc.exists() and GUARD_MARKER in rc.read_text(errors="ignore")


def install_autowrap(shell: str = "bash") -> Path:
    name = _RC_FILES.get(shell)
    if not name:
        raise GitUndoError(f"unsupported shell '{shell}' (supported: bash, zsh)")
    rc = Path.home() / name
    if is_autowrapped(shell):
        raise GitUndoError(f"auto-guard is already installed in ~/{name} (uninstall first)")
    rc.parent.mkdir(parents=True, exist_ok=True)
    text = rc.read_text(errors="ignore") if rc.exists() else ""
    with rc.open("a") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write(autowrap_block(shell))
    return rc


def uninstall_autowrap(shell: str = "bash") -> Path:
    name = _RC_FILES.get(shell)
    if not name:
        raise GitUndoError(f"unsupported shell '{shell}'")
    rc = Path.home() / name
    if not rc.exists() or not is_autowrapped(shell):
        raise GitUndoError(f"auto-guard is not installed in ~/{name}")
    text = rc.read_text(errors="ignore")
    first = text.find(GUARD_MARKER)
    second = text.find(GUARD_MARKER, first + len(GUARD_MARKER))
    end = (second + len(GUARD_MARKER)) if second != -1 else len(text)
    while end < len(text) and text[end] == "\n":
        end += 1
    new = text[:first].rstrip("\n") + "\n" + text[end:].lstrip("\n")
    rc.write_text(new)
    return rc
