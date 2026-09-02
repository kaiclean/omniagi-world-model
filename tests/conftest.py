"""Shared pytest fixtures.

Every test that mutates the harness works on a *temporary copy* pointed at by
``OMNIAGI_ROOT``. Nothing in the test suite may dirty the real working tree.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omniagi.paths import ENV_VAR, harness_root
from omniagi.registry import load_registry

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def registry():
    return load_registry()


@pytest.fixture
def temp_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A disposable copy of the harness, active for the duration of a test."""
    destination = tmp_path / "harness"
    shutil.copytree(
        harness_root(),
        destination,
        ignore=shutil.ignore_patterns(
            ".git", "__pycache__", ".venv", "runs", ".pytest_cache", ".mypy_cache", ".ruff_cache"
        ),
    )
    monkeypatch.setenv(ENV_VAR, str(destination))
    return destination


@pytest.fixture(autouse=True)
def _no_traces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not write run traces into the repository."""
    monkeypatch.setenv("OMNIAGI_NO_TRACE", "1")
