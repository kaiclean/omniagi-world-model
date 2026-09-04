"""Typed world-state memory tests."""

from __future__ import annotations

import pytest

from omniagi import worldstate
from omniagi.results import Status


def test_assert_and_get_roundtrip(temp_harness) -> None:
    worldstate.assert_fact("os", "linux", "string", source="probe", confidence=0.8)
    fact = worldstate.get_fact("os")
    assert fact is not None
    assert fact.value == "linux"
    assert fact.type == "string"
    assert fact.provenance.source == "probe"


def test_type_mismatch_is_rejected(temp_harness) -> None:
    with pytest.raises(worldstate.WorldStateError, match="does not match declared type"):
        worldstate.assert_fact("cpu", "eight", "integer", source="probe")


def test_unknown_type_is_rejected(temp_harness) -> None:
    with pytest.raises(worldstate.WorldStateError, match="unknown value type"):
        worldstate.assert_fact("cpu", 8, "int", source="probe")


def test_confidence_bounds_are_enforced(temp_harness) -> None:
    with pytest.raises(worldstate.WorldStateError, match="confidence"):
        worldstate.assert_fact("cpu", 8, "integer", source="probe", confidence=1.5)


def test_lower_confidence_conflict_keeps_existing(temp_harness) -> None:
    worldstate.assert_fact("cpu", 8, "integer", source="probe", confidence=0.9)
    resolution = worldstate.assert_fact("cpu", 4, "integer", source="guess", confidence=0.3)
    assert resolution.kept == "existing"
    fact = worldstate.get_fact("cpu")
    assert fact is not None
    assert fact.value == 8
    assert fact.history[-1]["value"] == 4


def test_higher_confidence_conflict_supersedes(temp_harness) -> None:
    worldstate.assert_fact("cpu", 8, "integer", source="probe", confidence=0.6)
    resolution = worldstate.assert_fact("cpu", 16, "integer", source="verified", confidence=0.95)
    assert resolution.kept == "incoming"
    fact = worldstate.get_fact("cpu")
    assert fact is not None
    assert fact.value == 16
    assert fact.history[-1]["value"] == 8


def test_confirming_value_keeps_higher_confidence(temp_harness) -> None:
    worldstate.assert_fact("cpu", 8, "integer", source="probe", confidence=0.6)
    resolution = worldstate.assert_fact("cpu", 8, "integer", source="probe2", confidence=0.9)
    assert resolution.kept == "incoming"
    fact = worldstate.get_fact("cpu")
    assert fact is not None
    assert fact.confidence == pytest.approx(0.9)
    assert fact.history == []


def test_missing_store_is_consistent(temp_harness) -> None:
    result = worldstate.check_world_state()
    assert result.status is Status.PASS
    assert "no world state" in result.summary


def test_check_flags_type_drift(temp_harness) -> None:
    worldstate.assert_fact("cpu", 8, "integer", source="probe")
    path = worldstate._store_path()
    text = path.read_text(encoding="utf-8").replace('"value": 8', '"value": "eight"')
    path.write_text(text, encoding="utf-8")
    result = worldstate.check_world_state()
    assert result.status is Status.FAIL
    assert any("does not match type" in detail for detail in result.details)


def test_malformed_json_fails_check(temp_harness) -> None:
    path = worldstate._store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    result = worldstate.check_world_state()
    assert result.status is Status.FAIL


def test_concurrent_asserts_serialize(temp_harness) -> None:
    import threading

    def worker(index: int) -> None:
        worldstate.assert_fact(f"k{index}", index, "integer", source="t", confidence=0.5)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stored = {fact.key for fact in worldstate.facts()}
    assert stored == {f"k{i}" for i in range(12)}
