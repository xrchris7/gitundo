"""Restore semantics: resurrection, conflict handling, safety guarantees."""

from __future__ import annotations

from gitundo import core


def _seed(repo):
    """Two snapshots, latest has the good state."""
    repo.write("a.txt", "v1")
    repo.commit("c0")
    core.snapshot(path=repo.path, message="cp1")
    repo.write("a.txt", "v2\nsecond line")
    repo.write("lost.txt", "precious")
    repo.write("tracked-del.txt", "bye")
    repo.git("add", "tracked-del.txt")
    core.snapshot(path=repo.path, message="cp2")
    repo.git("commit", "-qm", "c1")  # commit cp2's work so deletions are tracked


def test_resurrects_deleted_tracked_file(repo):
    _seed(repo)
    repo.git("rm", "-q", "tracked-del.txt")
    repo.rm("lost.txt")
    repo.write("a.txt", "v3")
    stats = core.restore(path=repo.path)
    # a.txt was edited locally -> kept aside, target still written
    assert stats["restored"] >= 3
    assert (repo.path / "lost.txt").read_text() == "precious"
    assert (repo.path / "tracked-del.txt").read_text() == "bye"
    # local edits are parked, not destroyed
    assert (repo.path / "a.txt.gitundo-keep").read_text() == "v3"


def test_restore_hard_overwrites_local_edits(repo):
    _seed(repo)
    repo.write("a.txt", "handwritten")
    stats = core.restore(path=repo.path, hard=True)
    assert stats["kept"] == 0
    assert repo.read("a.txt").startswith("v2")


def test_restore_never_touches_committed_history(repo):
    _seed(repo)
    head_before = repo.git("rev-parse", "HEAD").strip()
    branch_before = repo.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    core.restore(path=repo.path, hard=True)
    assert repo.git("rev-parse", "HEAD").strip() == head_before
    assert repo.git("rev-parse", "--abbrev-ref", "HEAD").strip() == branch_before


def test_untracked_files_survive_restore_by_default(repo):
    _seed(repo)
    repo.write("mine.txt", "do not touch")
    stats = core.restore(path=repo.path)
    assert (repo.path / "mine.txt").exists()
    assert stats["removed"] == 0


def test_delete_extraneous_removes_untracked_not_in_checkpoint(repo):
    _seed(repo)
    repo.write("scratch.tmp", "debris")
    stats = core.restore(path=repo.path, delete_extraneous=True)
    assert stats["removed"] == 1
    assert not (repo.path / "scratch.tmp").exists()


def test_restore_index_flag_resets_the_index(repo):
    _seed(repo)
    # advance HEAD so the index is "newer" than the latest checkpoint
    repo.write("a.txt", "v9")
    repo.commit("c2")
    assert repo.read("a.txt") == "v9"

    # without --index the staging area is left exactly as it was
    core.restore(path=repo.path, hard=True)
    assert "a.txt" not in repo.git("diff", "--cached", "--name-only").split()

    # make the worktree "newer" again, then restore with --index
    repo.write("a.txt", "v10")
    repo.git("add", "a.txt")
    core.restore(path=repo.path, index=True, hard=True)
    assert repo.read("a.txt").startswith("v2")
    # the index now matches the checkpoint, which differs from HEAD (v9)
    assert "a.txt" in repo.git("diff", "--cached", "--name-only").split()


def test_restore_by_number_and_oid(repo):
    _seed(repo)
    cps = repo.snapshots()
    core.restore(path=repo.path, selector="1")  # one before latest
    assert repo.read("a.txt").strip() == "v1"
    core.restore(path=repo.path, selector=cps[-1].oid[:7], hard=True)
    assert repo.read("a.txt").startswith("v2")


def test_restore_no_checkpoints_raises(repo):
    repo.write("a", "1")
    repo.commit("c0")
    try:
        core.restore(path=repo.path)
        raise AssertionError("expected NoCheckpoints")
    except core.NoCheckpoints:
        pass


def test_restore_unknown_selector_raises(repo):
    _seed(repo)
    try:
        core.restore(path=repo.path, selector="does-not-exist")
        raise AssertionError("expected NoCheckpoints")
    except core.NoCheckpoints:
        pass
