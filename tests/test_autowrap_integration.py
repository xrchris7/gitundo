"""End-to-end: the auto-guard shell wrapper really snapshots before damage."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from gitundo import core
from gitundo.core import CHECKPOINT_REF

pytestmark = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None, reason="shell guard integration needs bash"
)


def _write_shim(tmp_path: Path) -> Path:
    """A `gitundo` executable on PATH that runs the local source tree."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    src = str(Path(__file__).resolve().parent.parent / "src")
    shim = bindir / "gitundo"
    shim.write_text(
        f'#!/usr/bin/env bash\nexport PYTHONPATH="{src}"\nexec python3 -m gitundo "$@"\n'
    )
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    return bindir


def _bash(repo: Path, script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], cwd=repo, text=True, capture_output=True, env=env)


@pytest.fixture
def guard_home(tmp_path, monkeypatch):
    """A scratch $HOME with the auto-guard installed."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    core.install_autowrap("bash")
    return home


def test_guard_snapshots_before_reset_hard(tmp_path: Path, guard_home, monkeypatch):
    from tests.conftest import Repo

    repo = Repo(tmp_path / "r")
    repo.write("a.txt", "original")
    repo.commit("base")
    repo.write("a.txt", "precious-uncommitted-work")  # unstaged
    repo.write("secret-untracked.txt", "don't lose me")

    env = os.environ.copy()
    env["PATH"] = str(_write_shim(tmp_path)) + os.pathsep + env.get("PATH", "")

    proc = _bash(repo.path, 'source "$HOME/.bashrc"\ngit reset --hard >/dev/null', env)
    assert proc.returncode == 0, proc.stderr

    # a checkpoint was taken BEFORE the reset, so the lost work is recoverable
    assert repo.ref_count() == 1
    oid = repo.git("rev-parse", CHECKPOINT_REF).strip()
    assert repo.git("cat-file", "-p", f"{oid}:a.txt").strip() == "precious-uncommitted-work"
    assert repo.git("cat-file", "-p", f"{oid}:secret-untracked.txt").strip() == "don't lose me"
    # ...while the working tree was actually reset (the damage happened)
    assert repo.read("a.txt") == "original"


def test_guard_passes_normal_git_through(tmp_path: Path, guard_home):
    from tests.conftest import Repo

    repo = Repo(tmp_path / "r")
    repo.write("a.txt", "x")
    repo.commit("c1")
    repo.write("b.txt", "y")  # something to commit through the wrapper

    env = os.environ.copy()
    env["PATH"] = str(_write_shim(tmp_path)) + os.pathsep + env.get("PATH", "")

    proc = _bash(
        repo.path,
        'source "$HOME/.bashrc"\n'
        "git log --oneline\n"
        'git add -A && git commit -qm "guarded commit"\n',
        env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "c1" in proc.stdout
    # harmless git usage created no checkpoint noise
    assert repo.ref_count() == 0
    assert "guarded commit" in repo.git("log", "--format=%s")


def test_guard_respects_gitundo_disable(tmp_path: Path, guard_home):
    from tests.conftest import Repo

    repo = Repo(tmp_path / "r")
    repo.write("a.txt", "original")
    repo.commit("base")
    repo.write("a.txt", "dirty")

    env = os.environ.copy()
    env["PATH"] = str(_write_shim(tmp_path)) + os.pathsep + env.get("PATH", "")
    env["GITUNDO_DISABLE"] = "1"

    proc = _bash(repo.path, 'source "$HOME/.bashrc"\ngit reset --hard >/dev/null', env)
    assert proc.returncode == 0, proc.stderr
    assert repo.ref_count() == 0  # no snapshot, user asked to disable the guard
