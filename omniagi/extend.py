"""The self-extension protocol, implemented for real.

``workflows/tool-extension.md`` describes six steps. This module executes them
against the live harness and verifies each one with a read-back:

1. detect the gap        - the tool id must not already be registered
2. specify               - write ``tools/<id>.md``
3. implement (optional)  - reference a script
4. register              - add the tool to ``registry/harness.json``
5. verify                - re-read the registry and the spec from disk
6. log                   - append a deduplicated changelog entry

The demo variant runs the whole loop inside a temporary copy of the harness so
it can be shown off without ever dirtying the working tree - the old
``selfcheck.py`` mutated tracked files on every single run, including in CI.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import docgen
from .hashing import refresh_manifest_entries
from .memory import append_changelog
from .paths import ENV_VAR, harness_root, resolve
from .persistence import atomic_write_json, atomic_write_text, file_lock
from .registry import RegistryError, load_registry, registry_path

DEMO_TOOL_ID = "demo_url_summarizer"


class ExtensionError(RuntimeError):
    """Raised when the self-extension protocol cannot complete."""


class _Transaction:
    """Snapshot-and-restore guard for a set of files.

    Self-extension touches several files (the spec, the registry, every derived
    doc and the manifest). If any step fails - including the read-back
    verification - the whole change must be undone, or the harness is left in a
    partial state that fails its own checks. Every file is snapshotted before it
    is written and restored on rollback (deleted if it did not exist before).
    """

    def __init__(self) -> None:
        self._snapshots: dict[Path, bytes | None] = {}

    def track(self, path: Path | str) -> None:
        target = Path(path)
        if target not in self._snapshots:
            self._snapshots[target] = target.read_bytes() if target.exists() else None

    def rollback(self) -> None:
        for target, original in self._snapshots.items():
            if original is None:
                target.unlink(missing_ok=True)
            else:
                atomic_write_text(target, original.decode("utf-8"))


@dataclass
class ExtensionReport:
    tool_id: str
    root: str
    steps: list[str] = field(default_factory=list)
    verified: bool = False

    def step(self, message: str) -> None:
        self.steps.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "root": self.root,
            "steps": list(self.steps),
            "verified": self.verified,
        }


SPEC_TEMPLATE = """# Tool: {tool_id}
Added by the OmniAGI self-extension protocol on {today}.

## Purpose
{purpose}

## Inputs
- (document the input schema here)

## Outputs
- (document the output schema here)

## How to invoke
{invoke}

## Dependencies
- (list dependencies, or "none")

## Verification
- Run the invocation above with a trivial input and confirm a real, non-empty
  result plus a zero exit code. Never record success without that evidence.
"""


def extend_tool(
    tool_id: str,
    name: str,
    purpose: str,
    notes: str = "Added via the self-extension protocol",
    script: str | None = None,
) -> ExtensionReport:
    """Run the full protocol for ``tool_id`` against the current harness root."""
    if not tool_id.replace("_", "").isalnum() or not tool_id.islower():
        raise ExtensionError(
            f"invalid tool id {tool_id!r}: use lowercase letters, digits and underscores"
        )

    report = ExtensionReport(tool_id=tool_id, root=str(harness_root()))

    # 1. detect the gap
    registry = load_registry()
    if registry.tool(tool_id) is not None:
        raise ExtensionError(f"tool '{tool_id}' is already registered - no gap to fill")
    report.step(f"1. gap detected: '{tool_id}' is not registered")

    # 2. specify
    spec_rel = f"tools/{tool_id}.md"
    spec_path = resolve(spec_rel)
    if spec_path.exists():
        raise ExtensionError(f"spec already exists on disk but is unregistered: {spec_rel}")
    if script and not resolve(script).is_file():
        raise ExtensionError(f"declared script does not exist: {script}")
    invoke = (
        f"- CLI: `python3 -m omniagi.{Path(script).stem}`"
        if script
        else "- (document the invocation)"
    )

    # Everything below mutates files on disk. Snapshot each one first and hold an
    # exclusive lock on the registry so a failure - or a concurrent writer -
    # cannot leave a partial extension behind.
    txn = _Transaction()
    with file_lock(registry_path()):
        try:
            txn.track(spec_path)
            atomic_write_text(
                spec_path,
                SPEC_TEMPLATE.format(
                    tool_id=tool_id,
                    today=date.today().isoformat(),
                    purpose=purpose,
                    invoke=invoke,
                ),
            )
            report.step(f"2. wrote spec {spec_rel} ({spec_path.stat().st_size} bytes)")

            # 3/4. implement + register in the canonical registry
            txn.track(registry_path())
            data = json.loads(registry_path().read_text(encoding="utf-8"))
            data["tools"].append(
                {
                    "id": tool_id,
                    "name": name,
                    "spec": spec_rel,
                    "status": "active",
                    "script": script,
                    "notes": notes,
                }
            )
            atomic_write_json(registry_path(), data)
            report.step(f"3-4. registered '{tool_id}' in {registry_path().name}")

            # regenerate every derived table so nothing drifts
            for rel in docgen.BLOCKS:
                txn.track(resolve(rel))
            changed = docgen.generate()
            report.step(
                f"4b. regenerated derived docs: {', '.join(changed) if changed else 'no change'}"
            )

            # A logged extension may legitimately rewrite generated constitution
            # files. Re-record only those hashes, so unrelated drift is detected.
            from .hashing import manifest_path

            txn.track(manifest_path())
            rehashed = refresh_manifest_entries(changed)
            report.step(
                f"4c. manifest re-recorded: {', '.join(rehashed) if rehashed else 'no change'}"
            )

            # 5. verify by reading back from disk
            try:
                reloaded = load_registry()
            except RegistryError as exc:
                raise ExtensionError(
                    f"registry became invalid after extension: {exc}"
                ) from exc
            entry = reloaded.tool(tool_id)
            spec_body = spec_path.read_text(encoding="utf-8")
            verified = (
                entry is not None
                and tool_id in spec_body
                and f"`{tool_id}`" in resolve("TOOLS.md").read_text(encoding="utf-8")
            )
            report.verified = bool(verified)
            report.step(f"5. verified by read-back: {report.verified}")
            if not report.verified:
                raise ExtensionError(
                    f"verification failed for '{tool_id}' - refusing to log success"
                )
        except BaseException:
            txn.rollback()
            raise

    # 6. log (outside the transaction: only reached once the change is durable)
    logged = append_changelog(f"tool_added: {tool_id} ({purpose}) verified=True")
    report.step(f"6. changelog appended: {logged}")
    return report


@contextmanager
def temporary_harness() -> Iterator[Path]:
    """Copy the harness into a temp dir and point ``OMNIAGI_ROOT`` at it."""
    source = harness_root()
    previous = os.environ.get(ENV_VAR)
    with tempfile.TemporaryDirectory(prefix="omniagi-demo-") as tmp:
        destination = Path(tmp) / "harness"
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "runs", ".pytest_cache"),
        )
        os.environ[ENV_VAR] = str(destination)
        try:
            yield destination
        finally:
            if previous is None:
                os.environ.pop(ENV_VAR, None)
            else:
                os.environ[ENV_VAR] = previous


def demo() -> ExtensionReport:
    """Run the self-extension protocol in a throwaway harness copy."""
    with temporary_harness():
        return extend_tool(
            tool_id=DEMO_TOOL_ID,
            name="Summarize a URL (self-extension demo)",
            purpose="Fetch a URL and return a compact summary",
            notes="Created by the self-extension demo in a temporary harness",
        )
