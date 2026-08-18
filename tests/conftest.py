from __future__ import annotations

import itertools
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "samples" / "orderflow"
VARIANTS = ROOT / "samples" / "_variants"


def set_variant(root: Path, variant: str) -> None:
    for f in sorted((VARIANTS / variant / "orderflow").glob("*.py")):
        shutil.copy2(f, root / "orderflow" / f.name)


@pytest.fixture(autouse=True)
def _no_mock_delay(monkeypatch):
    """The mock's synthetic latency exists for the demo, not for the test suite."""
    monkeypatch.setenv("SPECGUARD_MOCK_DELAY", "0")


@pytest.fixture
def fixture_repo(tmp_path: Path):
    """A throwaway copy of samples/orderflow, so tests never touch the demo repo."""
    made = itertools.count()

    def build(variant: str = "clean") -> Path:
        # Unique per call: a test may want a clean and a drifted copy side by side.
        dest = tmp_path / f"orderflow-{next(made)}"
        shutil.copytree(
            FIXTURE,
            dest,
            ignore=shutil.ignore_patterns(".git", ".specguard", "__pycache__", ".pytest_cache"),
        )
        set_variant(dest, variant)
        return dest

    return build


@pytest.fixture
def git_fixture(fixture_repo):
    """The same copy, but with a real commit so git_state() has something to read."""

    def build(variant: str = "clean") -> Path:
        root = fixture_repo(variant)
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
            subprocess.run(["git", "-C", str(root), "config", k, v], check=True)
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(root), "commit", "-q", "-m", variant], check=True
        )
        return root

    return build
