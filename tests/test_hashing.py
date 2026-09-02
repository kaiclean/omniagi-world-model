"""Hashing and manifest tests.

The original ``file_hasher`` printed an error and exited zero, so CI reported a
green check for a broken tool.  These tests exist so that specific failure can
never come back: the failure paths are asserted, not just the happy path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omniagi import hashing
from omniagi.results import Status

HEX = set("0123456789abcdef")


def test_digest_matches_hashlib(temp_harness: Path) -> None:
    target = temp_harness / "sample.txt"
    target.write_text("omniagi", encoding="utf-8")
    expected = hashlib.sha256(b"omniagi").hexdigest()
    assert hashing.hash_file("sample.txt") == expected


def test_digest_is_64_hex_characters(temp_harness: Path) -> None:
    digest = hashing.hash_file("OmniAGI.md")
    assert len(digest) == 64
    assert set(digest) <= HEX


def test_missing_file_raises_instead_of_returning_a_sentinel(temp_harness: Path) -> None:
    with pytest.raises(hashing.HashError):
        hashing.hash_file("definitely-not-here.md")


def test_directory_is_not_hashable(temp_harness: Path) -> None:
    with pytest.raises(hashing.HashError):
        hashing.hash_file("tools")


def test_traversal_outside_the_root_is_refused(temp_harness: Path) -> None:
    with pytest.raises(hashing.HashError):
        hashing.hash_file("../../../../etc/passwd")


def test_absolute_path_outside_the_root_is_refused(temp_harness: Path) -> None:
    with pytest.raises(hashing.HashError):
        hashing.hash_file("/etc/hostname")


def test_empty_file_still_hashes(temp_harness: Path) -> None:
    (temp_harness / "empty.txt").write_bytes(b"")
    assert hashing.hash_file("empty.txt") == hashlib.sha256(b"").hexdigest()


def test_chunked_read_matches_single_shot(temp_harness: Path) -> None:
    """A file larger than CHUNK_SIZE must hash identically."""
    payload = b"x" * (hashing.CHUNK_SIZE * 2 + 17)
    (temp_harness / "large.bin").write_bytes(payload)
    assert hashing.hash_file("large.bin") == hashlib.sha256(payload).hexdigest()


def test_manifest_covers_every_constitution_file(temp_harness: Path, registry) -> None:
    manifest = hashing.build_manifest()
    assert set(manifest["files"]) == set(registry.constitution_files)
    assert manifest["algorithm"] == "sha256"


def test_repository_manifest_is_current() -> None:
    """The committed manifest must match the committed constitution."""
    assert hashing.check_manifest().status is Status.PASS


def test_manifest_detects_tampering(temp_harness: Path) -> None:
    hashing.write_manifest()
    assert hashing.check_manifest().status is Status.PASS

    target = temp_harness / "OmniAGI.md"
    target.write_text(target.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")

    result = hashing.check_manifest()
    assert result.status is Status.FAIL
    assert any("OmniAGI.md" in detail for detail in result.details)


def test_missing_manifest_is_reported_not_silently_accepted(temp_harness: Path) -> None:
    hashing.manifest_path().unlink()
    result = hashing.check_manifest()
    assert result.status is Status.FAIL
    assert "manifest.json" in result.summary


def test_write_manifest_is_idempotent(temp_harness: Path) -> None:
    first = hashing.write_manifest().read_text(encoding="utf-8")
    second = hashing.write_manifest().read_text(encoding="utf-8")
    assert first == second


def test_manifest_flags_a_file_it_does_not_record(temp_harness: Path) -> None:
    path = hashing.manifest_path()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    dropped = sorted(manifest["files"])[0]
    del manifest["files"][dropped]
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = hashing.check_manifest()
    assert result.status is Status.FAIL
    assert any(dropped in detail for detail in result.details)


def test_manifest_flags_a_recorded_file_that_disappeared(temp_harness: Path) -> None:
    hashing.write_manifest()
    (temp_harness / "OmniAGI.md").unlink()
    result = hashing.check_manifest()
    assert result.status is Status.FAIL
