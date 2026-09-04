"""SHA-256 hashing and the constitution hash manifest.

This backs two things:

* the ``file_hasher`` tool, which now fails loudly (non-zero exit, no
  "Error: ..." string printed on stdout with a success status), and
* ``memory/manifest.json``, which records the hash of every constitution file
  so tampering or accidental drift is detected instead of assumed away.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from .paths import harness_root, resolve
from .persistence import atomic_write_json, file_lock
from .registry import Registry, load_registry
from .results import CheckResult

MANIFEST_PATH = ("memory", "manifest.json")
CHUNK_SIZE = 1024 * 1024


class HashError(RuntimeError):
    """Raised when a file cannot be hashed."""


def manifest_path() -> Path:
    return resolve(*MANIFEST_PATH)


def _resolve_inside_root(rel_path: str | Path) -> Path:
    """Resolve ``rel_path`` and refuse to escape the harness root.

    The hasher is reachable from the CLI, so a caller-supplied path must not be
    able to read arbitrary files outside the harness via ``../`` traversal.
    """
    root = harness_root()
    candidate = Path(rel_path)
    target = candidate if candidate.is_absolute() else root / candidate
    target = target.resolve()
    if target != root and root not in target.parents:
        raise HashError(f"refusing to hash a path outside the harness root: {rel_path}")
    return target


def hash_file(rel_path: str | Path) -> str:
    """Return the SHA-256 hex digest of a harness file.

    Raises :class:`HashError` when the file is missing.  It never returns a
    sentinel string, because a sentinel that looks like output is precisely how
    the old implementation reported success for a broken tool.
    """
    target = _resolve_inside_root(rel_path)
    if not target.is_file():
        raise HashError(f"file not found: {rel_path}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(registry: Registry | None = None) -> dict[str, Any]:
    """Compute a fresh manifest for every constitution file."""
    reg = registry or load_registry()
    entries: dict[str, str] = {}
    missing: list[str] = []
    for rel in sorted(reg.constitution_files):
        try:
            entries[rel] = hash_file(rel)
        except HashError:
            missing.append(rel)
    if missing:
        raise HashError(
            "cannot build manifest, constitution files missing: " + ", ".join(missing)
        )
    return {
        "algorithm": "sha256",
        "generated_on": date.today().isoformat(),
        "files": entries,
    }


def write_manifest(registry: Registry | None = None) -> Path:
    """Write ``memory/manifest.json`` atomically and return its path."""
    manifest = build_manifest(registry)
    target = manifest_path()
    with file_lock(target):
        atomic_write_json(target, manifest, sort_keys=True)
    return target


def read_manifest() -> dict[str, Any] | None:
    target = manifest_path()
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def diff_manifest(registry: Registry | None = None) -> dict[str, list[str]]:
    """Return the drift between the recorded manifest and the working tree."""
    reg = registry or load_registry()
    recorded = read_manifest()
    if recorded is None:
        return {"missing_manifest": ["memory/manifest.json"], "changed": [], "added": [], "removed": []}

    recorded_files: dict[str, str] = recorded.get("files", {})
    changed: list[str] = []
    added: list[str] = []
    removed: list[str] = []

    for rel in sorted(reg.constitution_files):
        try:
            actual = hash_file(rel)
        except HashError:
            removed.append(rel)
            continue
        expected = recorded_files.get(rel)
        if expected is None:
            added.append(rel)
        elif expected != actual:
            changed.append(f"{rel}: recorded {expected[:12]}... actual {actual[:12]}...")

    for rel in sorted(recorded_files):
        if rel not in reg.constitution_files:
            removed.append(f"{rel} (recorded but no longer a constitution file)")

    return {"missing_manifest": [], "changed": changed, "added": added, "removed": removed}


def check_manifest(registry: Registry | None = None) -> CheckResult:
    """Report constitution hash drift as a named check."""
    name = "integrity.hash_manifest"
    drift = diff_manifest(registry)
    if drift["missing_manifest"]:
        return CheckResult.failed(
            name,
            "memory/manifest.json is missing - run 'omniagi hash --write-manifest'",
        )
    errors = [
        *(f"changed: {item}" for item in drift["changed"]),
        *(f"not recorded: {item}" for item in drift["added"]),
        *(f"missing/stale: {item}" for item in drift["removed"]),
    ]
    return CheckResult.from_errors(
        name,
        errors,
        "constitution hashes match memory/manifest.json",
        "constitution hash drift detected",
    )


def refresh_manifest_entries(rel_paths: list[str]) -> list[str]:
    """Re-record the hashes of ``rel_paths`` only, leaving the rest untouched.

    Used after a legitimate, logged change (self-extension regenerating derived
    constitution files).  Refreshing the *whole* manifest would silently bless
    unrelated tampering, so only the files actually rewritten are updated.
    """
    recorded = read_manifest()
    if recorded is None:
        return []
    reg = load_registry()
    updated: list[str] = []
    target = manifest_path()
    with file_lock(target):
        recorded = read_manifest()
        if recorded is None:
            return []
        for rel in rel_paths:
            if rel not in reg.constitution_files:
                continue
            digest = hash_file(rel)
            if recorded["files"].get(rel) != digest:
                recorded["files"][rel] = digest
                updated.append(rel)
        if updated:
            recorded["generated_on"] = date.today().isoformat()
            atomic_write_json(target, recorded, sort_keys=True)
    return updated
