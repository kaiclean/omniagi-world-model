"""Memory tests.

The anti-staleness rules were previously prose. These assert they are now
executable: an expired fact must fail CI, and host-specific state must never
reach the public durable memory.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from omniagi import memory
from omniagi.results import Status


def test_repository_memory_parses() -> None:
    entries = memory.parse_memory()
    assert entries, "MEMORY.md must contain structured entries"
    assert all(entry.id for entry in entries)
    assert all(entry.source for entry in entries)


def test_repository_memory_is_neither_expired_nor_leaky() -> None:
    assert memory.check_memory_expiry().status in {Status.PASS, Status.WARN}
    assert memory.check_memory_hygiene().status is Status.PASS
    assert memory.check_changelog().status is Status.PASS


def _write_memory(root: Path, rows: str) -> None:
    (root / "MEMORY.md").write_text(
        "# Memory\n\n"
        "| id | tag | fact | established | expires | source |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + rows,
        encoding="utf-8",
    )


def test_expired_entry_fails_the_audit(temp_harness: Path) -> None:
    stale = (date.today() - timedelta(days=1)).isoformat()
    _write_memory(temp_harness, f"| m-1 | env | something | 2020-01-01 | {stale} | test |\n")
    result = memory.check_memory_expiry()
    assert result.status is Status.FAIL
    assert any("m-1" in detail for detail in result.details)


def test_imminent_expiry_warns_but_does_not_fail(temp_harness: Path) -> None:
    soon = (date.today() + timedelta(days=3)).isoformat()
    _write_memory(temp_harness, f"| m-1 | env | something | 2020-01-01 | {soon} | test |\n")
    assert memory.check_memory_expiry().status is Status.WARN


def test_never_expiring_entry_passes(temp_harness: Path) -> None:
    _write_memory(temp_harness, "| m-1 | design | invariant | 2020-01-01 | never | test |\n")
    assert memory.check_memory_expiry().status is Status.PASS


def test_far_future_expiry_passes(temp_harness: Path) -> None:
    later = (date.today() + timedelta(days=365)).isoformat()
    _write_memory(temp_harness, f"| m-1 | env | something | 2020-01-01 | {later} | test |\n")
    assert memory.check_memory_expiry().status is Status.PASS


def test_duplicate_ids_are_rejected(temp_harness: Path) -> None:
    _write_memory(
        temp_harness,
        "| m-1 | a | x | 2020-01-01 | never | test |\n"
        "| m-1 | b | y | 2020-01-01 | never | test |\n",
    )
    with pytest.raises(memory.MemoryError_):
        memory.parse_memory()


def test_malformed_date_is_rejected(temp_harness: Path) -> None:
    _write_memory(temp_harness, "| m-1 | a | x | not-a-date | never | test |\n")
    with pytest.raises(memory.MemoryError_):
        memory.parse_memory()


def test_table_without_entries_is_an_error(temp_harness: Path) -> None:
    _write_memory(temp_harness, "")
    with pytest.raises(memory.MemoryError_):
        memory.parse_memory()


def test_hygiene_catches_a_host_path_leak(temp_harness: Path) -> None:
    target = temp_harness / "MEMORY.md"
    leak = "/Users/" + "someone/Projects/omniagi"
    target.write_text(target.read_text(encoding="utf-8") + f"\nRoot is {leak}\n", encoding="utf-8")
    result = memory.check_memory_hygiene()
    assert result.status is Status.FAIL
    assert any("local.md" in detail for detail in result.details)


def test_changelog_dedupe_collapses_consecutive_duplicates(temp_harness: Path) -> None:
    path = temp_harness / "memory" / "CHANGELOG.md"
    path.write_text("- 2026-01-01 same\n- 2026-01-01 same\n- 2026-01-01 same\n", encoding="utf-8")
    assert memory.dedupe_changelog(path) == 2
    assert path.read_text(encoding="utf-8").count("same") == 1


def test_changelog_dedupe_keeps_non_adjacent_repeats(temp_harness: Path) -> None:
    path = temp_harness / "memory" / "CHANGELOG.md"
    path.write_text("- a\n- b\n- a\n", encoding="utf-8")
    assert memory.dedupe_changelog(path) == 0


def test_append_skips_an_identical_consecutive_entry(temp_harness: Path) -> None:
    path = temp_harness / "memory" / "CHANGELOG.md"
    today = date(2026, 1, 1)
    assert memory.append_changelog("did a thing", path, today) is True
    assert memory.append_changelog("did a thing", path, today) is False
    assert path.read_text(encoding="utf-8").count("did a thing") == 1


def test_append_writes_a_different_entry(temp_harness: Path) -> None:
    path = temp_harness / "memory" / "CHANGELOG.md"
    today = date(2026, 1, 1)
    memory.append_changelog("first", path, today)
    assert memory.append_changelog("second", path, today) is True


def test_check_changelog_detects_injected_duplicates(temp_harness: Path) -> None:
    path = temp_harness / "memory" / "CHANGELOG.md"
    path.write_text("- 2026-01-01 dup\n- 2026-01-01 dup\n", encoding="utf-8")
    assert memory.check_changelog().status is Status.FAIL
