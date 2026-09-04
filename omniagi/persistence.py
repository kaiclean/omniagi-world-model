"""Atomic, lock-guarded persistence primitives.

The harness edits its own registry, manifest, memory and world state. A crash or
a second concurrent writer part-way through one of those writes would leave a
half-written JSON file that then fails to load - the harness would have corrupted
its own source of truth. Two guarantees remove that class of failure:

* **Atomic writes.** Content is written to a temporary file in the same
  directory, flushed and ``fsync``-ed, then ``os.replace``-d over the target.
  ``os.replace`` is atomic on POSIX and Windows, so a reader ever sees either the
  old file or the new one, never a truncated mix.
* **Advisory locks.** A ``flock`` on a sidecar ``<path>.lock`` serialises writers
  so two processes cannot interleave a read-modify-write of the same file.

Both are best-effort-portable: ``fcntl`` is used when present (POSIX), and the
atomic replace still holds on platforms without it.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:  # pragma: no cover - platform dependent
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

DEFAULT_LOCK_TIMEOUT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05


class PersistenceError(RuntimeError):
    """Raised when a locked write cannot be completed."""


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    """Write ``text`` to ``path`` atomically (temp file + fsync + replace)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def atomic_write_json(path: str | Path, data: Any, *, sort_keys: bool = False) -> Path:
    """Serialise ``data`` as pretty JSON and write it atomically."""
    return atomic_write_text(path, json.dumps(data, indent=2, sort_keys=sort_keys) + "\n")


@contextmanager
def file_lock(
    path: str | Path, *, timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS
) -> Iterator[None]:
    """Hold an exclusive advisory lock for ``path`` for the block's duration.

    The lock is taken on a sidecar ``<path>.lock`` file so the target itself is
    only ever touched by the atomic replace. On platforms without ``fcntl`` the
    context still runs (the atomic write remains safe); only cross-process
    serialisation is unavailable there.
    """
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("w", encoding="utf-8")
    try:
        if fcntl is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise PersistenceError(
                            f"timed out after {timeout:g}s acquiring lock on {path}"
                        ) from exc
                    time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        try:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def locked_json_update(
    path: str | Path,
    mutate: Callable[[Any], Any],
    *,
    default: Any = None,
    sort_keys: bool = False,
    timeout: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
) -> Any:
    """Read-modify-write a JSON file under an exclusive lock.

    ``mutate`` receives the parsed document (or ``default`` when the file does
    not yet exist) and returns the document to persist. The whole cycle happens
    while the lock is held, so concurrent writers cannot clobber one another.
    Returns the object that was written.
    """
    target = Path(path)
    with file_lock(target, timeout=timeout):
        current = (
            json.loads(target.read_text(encoding="utf-8")) if target.exists() else default
        )
        updated = mutate(current)
        atomic_write_json(target, updated, sort_keys=sort_keys)
        return updated
