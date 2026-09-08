"""Selectors, tags, prune and the destructive-command guard."""

from __future__ import annotations

import os

import pytest

from gitundo import core
from gitundo.core import GitUndoError

# The autowrap guard is a POSIX shell feature; these two tests exercise the
# generated bash block directly, so they only run where bash/POSIX semantics
# exist (Linux, macOS). Windows CI runs all other tests.
_skip_if_no_posix_shell = pytest.mark.skipif(
    os.name == "nt",
    reason="auto-guard is a POSIX shell feature",
)


def _mkrepo(repo, n: int = 3):
    repo.write("a", "1")
    repo.commit("c0")
    for i in range(n):
        repo.write("a", f"v{i}")
        core.snapshot(path=repo.path, message=f"cp{i}")


def test_selector_latest_and_numbers(repo):
    _mkrepo(repo)
    cps = repo.snapshots()
    assert core.find_checkpoint(repo.path, "latest").oid == cps[-1].oid
    assert core.find_checkpoint(repo.path, "0").oid == cps[-1].oid
    assert core.find_checkpoint(repo.path, "1").oid == cps[-2].oid
    assert core.find_checkpoint(repo.path, str(len(cps) - 1)).oid == cps[0].oid
    assert core.find_checkpoint(repo.path, "999") is None
    assert core.find_checkpoint(repo.path, "nope") is None


def test_selector_by_oid_prefix_and_tag(repo):
    _mkrepo(repo, 2)
    cps = repo.snapshots()
    core.add_tag(path=repo.path, name="golden", selector="0")
    # tagging doesn't rewrite the checkpoint: same oid, resolvable by tag
    assert core.find_checkpoint(repo.path, "golden").oid == cps[-1].oid
    assert core.find_checkpoint(repo.path, cps[0].oid[:6]).oid == cps[0].oid
    assert core.find_checkpoint(repo.path, "golden").tag == "golden"


def test_tag_validation(repo):
    _mkrepo(repo, 1)
    with pytest.raises(GitUndoError):
        core.add_tag(path=repo.path, name="bad name!")
    with pytest.raises(GitUndoError):
        core.add_tag(path=repo.path, name="x" * 65)
    with pytest.raises(GitUndoError):
        core.add_tag(path=repo.path, name="1bad_start?no")


def test_tag_duplicate_rejected(repo):
    _mkrepo(repo, 2)
    core.add_tag(path=repo.path, name="golden", selector="0")
    with pytest.raises(GitUndoError):
        core.add_tag(path=repo.path, name="golden", selector="1")


def test_tag_untag_keeps_chain_integrity(repo):
    _mkrepo(repo, 2)
    core.add_tag(path=repo.path, name="t1", selector="0")
    core.remove_tag(path=repo.path, name="t1")
    # chain intact, ref intact, list healthy
    assert repo.ref_count() == 2
    assert core.find_checkpoint(repo.path, "0").tag == ""
    assert core.find_checkpoint(repo.path, "latest").tag == ""


def test_retag_does_not_rewrite_branch(repo):
    _mkrepo(repo, 1)
    head = repo.git("rev-parse", "HEAD").strip()
    core.add_tag(path=repo.path, name="t1")
    assert repo.git("rev-parse", "HEAD").strip() == head


# --------------------------------------------------------------------------- #
# prune
# --------------------------------------------------------------------------- #


def test_prune_keeps_newest(repo):
    _mkrepo(repo, 6)
    removed = core.prune(path=repo.path, keep=2)
    assert removed == 4
    cps = repo.snapshots()
    assert len(cps) == 2
    assert repo.ref_count() == 2
    # newest content still restorable
    core.restore(path=repo.path, selector="0", hard=True)
    assert repo.read("a") == "v5"


def test_prune_protects_tagged(repo):
    _mkrepo(repo, 5)
    core.add_tag(path=repo.path, name="keep-me", selector="2")
    removed = core.prune(path=repo.path, keep=1)
    assert removed == 3  # tag protected the middle one
    cps = repo.snapshots()
    assert len(cps) == 2  # newest + tagged one
    assert sorted(c.tag for c in cps) == ["", "keep-me"]
    assert "keep-me" in {c.tag for c in cps}


def test_prune_refuses_to_delete_everything(repo):
    _mkrepo(repo, 1)
    core.add_tag(path=repo.path, name="only", selector="0")
    with pytest.raises(GitUndoError):
        core.prune(path=repo.path, keep=0, protected_tags=False)


def test_prune_nothing_to_do(repo):
    _mkrepo(repo, 3)
    assert core.prune(path=repo.path, keep=100) == 0


# --------------------------------------------------------------------------- #
# guard
# --------------------------------------------------------------------------- #

DANGEROUS = [
    ("git reset --hard", "git reset --hard"),
    ("git reset --hard HEAD~2", "git reset --hard"),
    ("git clean -fdx", "git clean -dfx"),
    ("git clean -fd", "git clean -dfx"),
    ("git checkout --force .", "git checkout --force"),
    ("git checkout -f", "git checkout --force"),
    ("git checkout .", "git checkout . (discard)"),
    ("git checkout -- .", "git checkout -- (discard)"),
    ("git checkout HEAD -- src/", "git checkout <ref> -- <path>"),
    ("git restore .", "git restore"),
    ("git rm -r dir", "git rm"),
    ("git branch -D old", "git branch -D"),
    ("rm -rf build", "rm -r/-f"),
    ("rm -r node_modules", "rm -r/-f"),
    ("rmdir emptydir", "rmdir"),
    ("shred secret.txt", "shred"),
    ("mv src dest", "mv / cp"),
    ("cp -r a b", "mv / cp"),
    ("truncate -s 0 big.log", "truncate / dd"),
    ("sed -i 's/x/y/' f.txt", "in-place text edit"),
]

# history-only operations are intentionally NOT guarded (reflog protects them)
NOT_GUARDED = [
    "git rebase main",
    "git revert HEAD",
    "git cherry-pick abc123",
    "git merge feature",
    "git reset --soft HEAD~1",
    "git commit -m 'reset config'",
    "git status",
    "git log --oneline",
    "git diff",
    "git add -A",
    "git checkout feature",
    "ls",
    "cat README.md",
    "git push origin main",
    "rmdir_is_not_a_command",
    "grep -r 'rm -rf' .",
    "echo hi > file.txt",
]


@pytest.mark.parametrize("cmd,label", DANGEROUS)
def test_guard_flags_dangerous(cmd, label):
    assert core.describe_danger(cmd) == label


@pytest.mark.parametrize("cmd", NOT_GUARDED)
def test_guard_ignores_others(cmd):
    assert core.describe_danger(cmd) is None


def test_guard_blank_and_comments():
    assert core.describe_danger("") is None
    assert core.describe_danger("# git reset --hard") is None
    assert core.describe_danger("   ") is None


# --------------------------------------------------------------------------- #
# autowrap
# --------------------------------------------------------------------------- #


@_skip_if_no_posix_shell
def test_autowrap_install_uninstall_roundtrip(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    home = tmp_path / "home"
    home.mkdir()
    rc = home / ".bashrc"

    # nothing installed yet
    assert core.is_autowrapped("bash") is False

    # install writes a guarded, idempotent block
    core.install_autowrap("bash")
    text = rc.read_text()
    assert core.GUARD_MARKER in text
    assert "git() {" in text and "command gitundo _guard_git" in text
    with pytest.raises(GitUndoError):
        core.install_autowrap("bash")  # already installed

    # uninstall removes the whole block
    core.uninstall_autowrap("bash")
    assert core.is_autowrapped("bash") is False
    assert core.GUARD_MARKER not in rc.read_text()


@_skip_if_no_posix_shell
def test_autowrap_block_is_valid_bash(repo, tmp_path):
    block = core.autowrap_block("bash")
    script = tmp_path / "check.sh"
    script.write_text("#!/bin/bash\n" + block + "\ncommand -v gitundo_guard\necho OK\n")
    import subprocess

    proc = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
