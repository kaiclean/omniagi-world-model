"""Structured JSON run traces.

Every CLI invocation writes a newline-delimited JSON trace under ``runs/``
(gitignored) so an agent loop can be audited after the fact. Without traces the
harness is a specification; with them it is an observable system.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import resolve

RUNS_DIRNAME = "runs"
DISABLE_VAR = "OMNIAGI_NO_TRACE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Trace:
    """Append-only JSONL trace for a single run."""

    def __init__(self, command: str, run_id: str | None = None) -> None:
        self.command = command
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.enabled = os.environ.get(DISABLE_VAR, "") == ""
        self.path: Path | None = None
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
        record = {
            "ts": _now(),
            "run_id": self.run_id,
            "command": self.command,
            "kind": kind,
            **fields,
        }
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
        except OSError:
            self.enabled = False

    def __enter__(self) -> Trace:
        self.event("start")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is None:
            self.event("end", status="ok")
        else:
            self.event("end", status="error", error=f"{exc_type.__name__}: {exc}")
