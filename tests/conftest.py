"""Shared fixtures: build real throwaway git repositories and drive gitundo."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# make `gitundo` importable when tests run from the repository root
SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "NO_COLOR": "1",
    "HOME": str(Path.home()),  # keep autowrap tests isolated instead
}


class Repo:
    """Tiny helper around a real git repository on disk."""

    def __init__(self, path: Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("config", "commit.gpgsign", "false")

    # -- plumbing ----------------------------------------------------------
    def git(self, *args: str, check: bool = True) -> str:
        env = os.environ.copy()
        env.update(ENV)
        proc = subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=env,
            text=True,
            capture_output=True,
        )
        if check and proc.returncode != 0:
            raise AssertionError(
                f"git {' '.join(args)!r} failed ({proc.returncode}):\n{proc.stderr}"
            )
        return proc.stdout

    def write(self, rel: str, content: str = "x") -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def write_bytes(self, rel: str, data: bytes) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text()

    def rm(self, rel: str) -> None:
        (self.path / rel).unlink()

    def commit(self, msg: str = "commit") -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD").strip()

    # -- gitundo ------------------------------------------------------------
    def gu_cli(self, *args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update(ENV)
        env["PYTHONPATH"] = str(SRC)
        proc = subprocess.run(
            [sys.executable, "-m", "gitundo", *args],
            cwd=self.path,
            env=env,
            text=True,
            capture_output=True,
        )
        return proc

    def snapshots(self) -> list:
        from gitundo import core

        return core.read_checkpoints(self.path)

    @property
    def ref(self) -> str:
        return self.git("rev-parse", "refs/gitundo/checkpoints").strip()

    def ref_count(self) -> int:
        out = self.git("rev-list", "--count", "refs/gitundo/checkpoints", check=False)
        return int(out.strip() or 0)

    def status(self) -> str:
        return self.git("status", "--porcelain", check=False)

    def tree(self, treeish: str) -> list[str]:
        """Paths in a tree/commit."""
        return self.git("ls-tree", "-r", "--name-only", treeish).split()

    def blob(self, ref: str) -> str:
        """Content of a git object (e.g. '<oid>:path')."""
        return self.git("cat-file", "-p", ref)

    def who(self, oid: str) -> str:
        """author name/email of a commit."""
        return self.git("log", "-1", "--format=%an%x1f%ae", oid)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo")
