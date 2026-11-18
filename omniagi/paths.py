"""Harness root resolution.

The harness root is resolved in this order:

1. ``OMNIAGI_ROOT`` environment variable (absolute or relative path)
2. the parent of the installed ``omniagi`` package (repository checkout)

No machine-specific path is ever hardcoded: the harness must run identically on
any host, which is exactly the class of bug this module exists to prevent.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "OMNIAGI_ROOT"


def harness_root() -> Path:
    """Return the absolute path to the harness root directory."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def resolve(*parts: str) -> Path:
    """Resolve a harness-relative path to an absolute path."""
    return harness_root().joinpath(*parts)


def relative(path: Path) -> str:
    """Render ``path`` relative to the harness root when possible."""
    try:
        return str(Path(path).resolve().relative_to(harness_root()))
    except ValueError:
        return str(path)


class WriteNotApproved(PermissionError):
    """Raised when a write outside the harness root lacks explicit approval."""


def guard_write(target: Path, approved: bool = False) -> Path:
    """Return ``target`` resolved, refusing writes outside the harness root.

    Writes inside the workspace are routine. A write that leaves it has an
    effect beyond this repository, so the caller must pass ``approved=True`` as
    the record of an explicit human decision.
    """
    resolved = Path(target).expanduser().resolve()
    root = harness_root()
    if resolved != root and root not in resolved.parents and not approved:
        raise WriteNotApproved(
            f"write outside the harness root needs explicit approval: {resolved}"
        )
    return resolved
