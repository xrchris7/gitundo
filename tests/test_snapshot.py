"""Snapshot behaviour against real git repositories."""

from __future__ import annotations

import os

import pytest

from gitundo import CHECKPOINT_REF, core
from gitundo.core import NothingToSnapshot


def snap(repo, message="cp", tag=None, **kw):
    return core.snapshot(path=repo.path, message=message, tag=tag, **kw)


def test_captures_untracked_before_first_commit(repo):
    repo.write("a.txt", "hello")
    repo.write("dir/b.txt", "nested")
    res = snap(repo, "first")
    assert res["created"] is True and res["untracked"] == 2
    cps = repo.snapshots()
    assert len(cps) == 1
    tree = repo.tree(cps[0].oid)
    assert "a.txt" in tree and "dir/b.txt" in tree


def test_captures_staged_unstaged_untracked_and_deletions(repo):
    repo.write("base.txt", "v1")
    repo.write("keep.txt", "k")
    repo.commit("c0")

    repo.write("staged.txt", "staged-content")
    repo.git("add", "staged.txt")
    repo.write("unstaged.txt", "worktree-content")  # created + unstaged
    repo.write("untracked.txt", "u")
    repo.write("base.txt", "v2")  # modified, unstaged
    repo.rm("keep.txt")  # deleted on disk
    repo.write("deleted-but-cached.txt", "x")
    repo.git("add", "deleted-but-cached.txt")
    repo.git("rm", "-q", "--cached", "deleted-but-cached.txt")  # staged deletion

    res = snap(repo)
    assert res["created"] is True
    cp = repo.snapshots()[-1]
    entries = repo.tree(cp.oid)
    # everything on disk is present ...
    for want in ("staged.txt", "unstaged.txt", "untracked.txt", "base.txt"):
        assert want in entries
    # ... including the file that is only in the index (staged deletion)
    assert "deleted-but-cached.txt" in entries
    # ... and the file deleted on disk is gone from the snapshot
    assert "keep.txt" not in entries
    assert "keep.txt" in repo.tree("HEAD")


def test_ignored_files_not_captured(repo):
    repo.write(".gitignore", "ignored.log\nbuild/\n")
    repo.write("kept.txt", "k")
    repo.commit("c0")
    repo.write("ignored.log", "noise")
    repo.write("build/out.bin", "noise")
    repo.write("visible.txt", "v")
    res = snap(repo)
    assert res["untracked"] == 1
    cp = repo.snapshots()[-1]
    entries = repo.tree(cp.oid)
    assert "visible.txt" in entries
    assert "ignored.log" not in entries
    assert "build/out.bin" not in entries


def test_symlink_and_binary_roundtrip(repo):
    repo.write("target.txt", "payload")
    (repo.path / "link.txt").symlink_to("target.txt")
    repo.write_bytes("blob.bin", bytes(range(256)))
    res = snap(repo, "bins")
    assert res["created"]
    # simulate loss, then restore
    for name in ("link.txt", "blob.bin"):
        (repo.path / name).unlink()
    core.restore(path=repo.path)
    assert (repo.path / "link.txt").is_symlink()
    assert os.readlink(repo.path / "link.txt") == "target.txt"
    assert (repo.path / "blob.bin").read_bytes() == bytes(range(256))


def test_empty_when_nothing_changed(repo):
    repo.write("a", "1")
    repo.commit("c0")
    snap(repo, "one")
    res = snap(repo, "two")  # no changes since
    assert res["created"] is False and res["empty"] is True
    assert repo.ref_count() == 1


def test_committed_changes_are_captured_after_snapshot(repo):
    repo.write("a", "1")
    repo.commit("c0")
    first = snap(repo, "one")
    repo.write("a", "2")
    repo.commit("c1")  # clean tree, but HEAD advanced
    second = snap(repo, "two")
    assert second["created"] is True
    cp = repo.snapshots()[-1]
    assert repo.blob(f"{cp.oid}:a").strip() == "2"
    assert first["oid"] != second["oid"]


def test_force_creates_even_when_unchanged(repo):
    repo.write("a", "1")
    repo.commit("c0")
    snap(repo)
    res = snap(repo, force=True)
    assert res["created"] is True
    assert repo.ref_count() == 2


def test_snapshot_never_touches_index_or_head(repo):
    repo.write("a", "1")
    repo.write("b", "2")
    repo.git("add", "a")  # staged
    repo.write("b", "changed")  # unstaged edit
    before_index = repo.git("diff", "--cached", "--name-only").split()
    before_head = repo.git("rev-parse", "HEAD", check=False).strip()
    repo.write("untracked", "u")
    snap(repo)
    # staging area untouched
    assert repo.git("diff", "--cached", "--name-only").split() == before_index
    # HEAD untouched (still unborn -> same empty output)
    assert repo.git("rev-parse", "HEAD", check=False).strip() == before_head
    # worktree untouched
    assert repo.read("b") == "changed"
    # checkpoint authors are gitundo, not the user
    cp = repo.snapshots()[-1]
    who = repo.who(cp.oid)
    assert who.strip() == "gitundo\x1fgitundo@localhost"


def test_checkpoint_chain_is_linear_and_rooted_in_ref(repo):
    repo.write("a", "1")
    repo.commit("c0")
    for i in range(4):
        repo.write("a", f"{i + 2}")
        snap(repo, f"cp{i}")
    assert repo.ref_count() == 4
    # every checkpoint commit is reachable through the ref
    raw = repo.git("rev-list", CHECKPOINT_REF)
    listed = raw.split()
    oids = {c.oid for c in repo.snapshots()}
    assert oids == set(listed)


def test_checkpoint_commits_have_snapshot_of_metadata(repo):
    repo.write("a", "1")
    repo.commit("c0")
    head = repo.git("rev-parse", "HEAD").strip()
    snap(repo)
    cp = repo.snapshots()[0]
    assert cp.snapshot_of == head


def test_empty_repo_raises_nothing(repo):
    with pytest.raises(NothingToSnapshot):
        snap(repo)


def test_outside_repo_raises(repo, tmp_path):
    with pytest.raises(core.NotARepository):
        core.snapshot(path=tmp_path / "nope")


def test_no_temp_index_left_behind(repo):
    repo.write("a", "1")
    repo.commit("c0")
    repo.write("b", "2")
    snap(repo)
    leftovers = [p for p in repo.path.iterdir() if ".gitundo" in p.name]
    assert leftovers == []
