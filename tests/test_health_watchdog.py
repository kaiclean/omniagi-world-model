"""Health probe, watchdog, trace and adapter tests.

The claim "cloud down → fall back to local" was documented intent. These tests
assert it is an executed decision, and — more importantly — that an unreachable
seat produces a refusal rather than fabricated output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import adapters, health, trace, watchdog
from omniagi.results import Status

# -- health --------------------------------------------------------------------


def test_local_seats_are_not_assumed_available(registry) -> None:
    """Without a probe, a local seat must report unknown, not available."""
    local = next(seat for seat in registry.seats if seat["tier"] == "local")
    probe = health.probe_seat(local, probe_network=False)
    assert probe.available is False
    assert "not probed" in probe.reason


def test_cloud_seat_without_credentials_is_unavailable(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    cloud = next(seat for seat in registry.seats if seat["tier"] != "local")
    probe = health.probe_seat(cloud)
    assert probe.available is False
    assert "credential" in probe.reason


def test_cloud_seat_with_credential_is_available(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(health.CLOUD_CREDENTIAL_VARS[0], "not-a-real-key")
    cloud = next(seat for seat in registry.seats if seat["tier"] != "local")
    assert health.probe_seat(cloud).available is True


def test_every_probe_carries_a_reason(registry) -> None:
    """A verdict without evidence is exactly what the constitution forbids."""
    assert all(probe.reason for probe in health.probe_all(registry))


def test_selection_returns_none_when_nothing_is_reachable(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    assert health.select_available_seat(registry.seats[0]["id"], registry) is None


def test_selection_prefers_the_requested_seat_when_usable(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(health.CLOUD_CREDENTIAL_VARS[0], "not-a-real-key")
    cloud = next(seat for seat in registry.seats if seat["tier"] != "local")
    chosen = health.select_available_seat(cloud["id"], registry)
    assert chosen is not None and chosen.seat_id == cloud["id"]


def test_selection_falls_back_when_the_preferred_seat_is_down(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(health.CLOUD_CREDENTIAL_VARS[0], "not-a-real-key")
    local = next(seat for seat in registry.seats if seat["tier"] == "local")
    chosen = health.select_available_seat(local["id"], registry)
    assert chosen is not None
    assert chosen.seat_id != local["id"]
    assert chosen.available is True


def test_health_check_warns_offline_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An offline CI runner is expected; a dishonest probe would not be."""
    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    assert health.check_health_probe().status is Status.WARN


def test_unreachable_endpoint_is_reported_unreachable() -> None:
    assert health._tcp_reachable("http://127.0.0.1:1", timeout=0.2) is False


# -- adapters ------------------------------------------------------------------


def test_adapter_refuses_instead_of_fabricating(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(adapters.SeatUnavailable):
        adapters.call_with_fallback("summarise this", preferred_seat="local_scout")


# -- watchdog ------------------------------------------------------------------


def test_watchdog_once_passes_on_a_healthy_harness(temp_harness: Path) -> None:
    alerts: list[str] = []
    config = watchdog.WatchdogConfig(log_path=temp_harness / "memory" / "watchdog.log")
    assert watchdog.check_once(config, sink=alerts.append) == 0
    assert alerts == []
    assert "PASSED" in config.log_path.read_text(encoding="utf-8")


def test_watchdog_alerts_on_a_broken_harness(temp_harness: Path) -> None:
    (temp_harness / "OmniAGI.md").write_text("tampered\n", encoding="utf-8")
    alerts: list[str] = []
    config = watchdog.WatchdogConfig(log_path=temp_harness / "memory" / "watchdog.log")

    assert watchdog.check_once(config, sink=alerts.append) == 1
    assert len(alerts) == 1
    assert "FAILED" in alerts[0]
    assert "ALERT" in config.log_path.read_text(encoding="utf-8")


def test_watchdog_backs_off_exponentially(temp_harness: Path) -> None:
    (temp_harness / "OmniAGI.md").write_text("tampered\n", encoding="utf-8")
    delays: list[float] = []
    config = watchdog.WatchdogConfig(
        interval=10.0, max_backoff=40.0, log_path=temp_harness / "memory" / "watchdog.log"
    )

    watchdog.watch(config, sink=lambda _: None, sleep=delays.append, iterations=4)

    assert delays == [20.0, 40.0, 40.0]  # doubles, then clamps at max_backoff


def test_watchdog_resets_backoff_after_recovery(temp_harness: Path) -> None:
    delays: list[float] = []
    config = watchdog.WatchdogConfig(
        interval=10.0, log_path=temp_harness / "memory" / "watchdog.log"
    )
    watchdog.watch(config, sink=lambda _: None, sleep=delays.append, iterations=3)
    assert delays == [10.0, 10.0]


def test_watchdog_strict_mode_treats_warnings_as_failures(temp_harness: Path) -> None:
    """Warnings are tolerable by default and fatal when explicitly requested."""
    config = watchdog.WatchdogConfig(
        strict=True, log_path=temp_harness / "memory" / "watchdog.log"
    )
    lenient = watchdog.WatchdogConfig(log_path=temp_harness / "memory" / "watchdog.log")
    from omniagi.selfcheck import run_checks

    if run_checks().warned:
        assert watchdog.check_once(config, sink=lambda _: None) == 1
    assert watchdog.check_once(lenient, sink=lambda _: None) == 0


# -- traces --------------------------------------------------------------------


def test_trace_is_disabled_by_the_env_var(temp_harness: Path) -> None:
    with trace.Trace("check") as tracer:
        tracer.event("decision", specialist="coder")
    assert tracer.enabled is False
    assert not (temp_harness / "runs").exists()


def test_trace_writes_jsonl_when_enabled(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(trace.DISABLE_VAR, raising=False)
    with trace.Trace("route") as tracer:
        tracer.event("decision", specialist="coder")

    assert tracer.path is not None
    records = [json.loads(line) for line in tracer.path.read_text(encoding="utf-8").splitlines()]
    kinds = [record["kind"] for record in records]
    assert kinds == ["start", "decision", "end"]
    assert records[-1]["status"] == "ok"
    assert all(record["run_id"] == tracer.run_id for record in records)


def test_trace_records_an_error_outcome(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(trace.DISABLE_VAR, raising=False)
    with pytest.raises(ValueError), trace.Trace("route") as tracer:
        raise ValueError("boom")

    assert tracer.path is not None
    last = json.loads(tracer.path.read_text(encoding="utf-8").splitlines()[-1])
    assert last["status"] == "error"
    assert "boom" in last["error"]
