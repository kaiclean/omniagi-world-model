"""Structured, tamper-evident JSON run traces.

Every CLI invocation writes a newline-delimited JSON trace under ``runs/``
(gitignored) so an agent loop can be audited after the fact. Without traces the
harness is a specification; with them it is an observable system.

Each event is chained to the one before it with a SHA-256 hash: a record carries
its sequence number, the hash of the previous event (``prev``) and its own
``hash`` computed over the rest of the record. Editing, reordering, inserting or
deleting any event breaks the chain, so :func:`audit_trace` can prove after the
fact that a trace was not tampered with.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import resolve

RUNS_DIRNAME = "runs"
DISABLE_VAR = "OMNIAGI_NO_TRACE"
GENESIS_HASH = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _digest(record: dict[str, Any]) -> str:
    """Canonical SHA-256 over a record, excluding its own ``hash`` field."""
    core = {key: value for key, value in record.items() if key != "hash"}
    encoded = json.dumps(core, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Trace:
    """Append-only, hash-chained JSONL trace for a single run."""

    def __init__(self, command: str, run_id: str | None = None) -> None:
        self.command = command
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.enabled = os.environ.get(DISABLE_VAR, "") == ""
        self.path: Path | None = None
        self._prev = GENESIS_HASH
        self._seq = 0
        if self.enabled:
            directory = resolve(RUNS_DIRNAME)
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.path = directory / f"{datetime.now(timezone.utc):%Y%m%d}-{self.run_id}.jsonl"
            except OSError:
                # A read-only checkout must not break the command being traced.
                self.enabled = False

    def event(self, kind: str, **fields: Any) -> None:
        if not self.enabled or self.path is None:
            return
        record: dict[str, Any] = {
            "ts": _now(),
            "run_id": self.run_id,
            "command": self.command,
            "kind": kind,
            "seq": self._seq,
            "prev": self._prev,
            **fields,
        }
        record["hash"] = _digest(record)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
        except OSError:
            self.enabled = False
            return
        self._prev = record["hash"]
        self._seq += 1

    def __enter__(self) -> Trace:
        self.event("start")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.event("end", status="ok")
        else:
            self.event("end", status="error", error=f"{exc_type.__name__}: {exc}")


# -- audit ---------------------------------------------------------------------


@dataclass(frozen=True)
class AuditResult:
    """Outcome of verifying the hash chain of a single trace file."""

    path: str
    events: int
    ok: bool
    errors: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "events": self.events,
            "ok": self.ok,
            "errors": list(self.errors),
        }


def verify_records(records: list[dict[str, Any]]) -> list[str]:
    """Return integrity violations found in a trace (empty when intact)."""
    errors: list[str] = []
    prev = GENESIS_HASH
    for index, record in enumerate(records):
        stored = record.get("hash")
        if not isinstance(stored, str):
            errors.append(f"event {index} has no hash")
            prev = GENESIS_HASH
            continue
        if _digest(record) != stored:
            errors.append(f"event {index} ({record.get('kind', '?')}) content was altered")
        if record.get("seq") != index:
            errors.append(f"event {index} has an out-of-order sequence number")
        if record.get("prev") != prev:
            errors.append(f"event {index} breaks the hash chain (prev mismatch)")
        prev = stored
    return errors


def read_trace(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def audit_trace(path: Path) -> AuditResult:
    """Audit a single JSONL trace for tamper-evidence."""
    try:
        records = read_trace(path)
    except (OSError, json.JSONDecodeError) as exc:
        return AuditResult(str(path), 0, ok=False, errors=[f"unreadable trace: {exc}"])
    errors = verify_records(records)
    return AuditResult(str(path), len(records), ok=not errors, errors=errors)


def iter_trace_files(directory: Path | None = None) -> list[Path]:
    root = directory or resolve(RUNS_DIRNAME)
    if not root.is_dir():
        return []
    return sorted(root.glob("*.jsonl"))


def audit_all(directory: Path | None = None) -> list[AuditResult]:
    return [audit_trace(path) for path in iter_trace_files(directory)]
