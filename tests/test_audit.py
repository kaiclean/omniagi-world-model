"""Tamper-evident trace hash-chain tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import cli, selfcheck, trace
from omniagi.results import Status


def _write_trace(temp_harness: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a small intact trace into the temp harness and return its path."""
    monkeypatch.delenv(trace.DISABLE_VAR, raising=False)
    with trace.Trace("route") as tracer:
        tracer.event("decision", specialist="coder")
        tracer.event("observation", note="ran a check")
    assert tracer.path is not None
    return tracer.path


def test_first_event_chains_to_genesis(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    records = trace.read_trace(path)
    assert records[0]["prev"] == trace.GENESIS_HASH
    assert records[0]["seq"] == 0
    assert all("hash" in record for record in records)


def test_intact_trace_passes_audit(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    result = trace.audit_trace(path)
    assert result.ok is True
    assert result.events == 4  # start, decision, observation, end
    assert result.errors == []


def test_altered_content_is_detected(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["specialist"] = "tampered"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = trace.audit_trace(path)
    assert result.ok is False
    assert any("altered" in error for error in result.errors)


def test_deleting_an_event_breaks_the_chain(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = trace.audit_trace(path)
    assert result.ok is False
    assert any("chain" in error or "sequence" in error for error in result.errors)


def test_reordering_events_breaks_the_chain(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = trace.audit_trace(path)
    assert result.ok is False


def test_verify_records_accepts_empty() -> None:
    assert trace.verify_records([]) == []


def test_read_trace_ignores_blank_lines(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    records = trace.read_trace(path)
    assert len(records) == 4


def test_audit_all_and_iter_trace_files(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_trace(temp_harness, monkeypatch)
    files = trace.iter_trace_files()
    assert files and all(p.suffix == ".jsonl" for p in files)
    audits = trace.audit_all()
    assert audits and all(a.ok for a in audits)


def test_audit_all_empty_when_no_runs(temp_harness: Path) -> None:
    runs = temp_harness / "runs"
    if runs.exists():
        for file in runs.glob("*.jsonl"):
            file.unlink()
    assert trace.audit_all() == []


def test_audit_result_to_dict(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    payload = trace.audit_trace(path).to_dict()
    assert set(payload) == {"path", "events", "ok", "errors"}
    assert payload["ok"] is True


def test_unreadable_trace_reports_error(tmp_path: Path) -> None:
    bogus = tmp_path / "broken.jsonl"
    bogus.write_text("{not json}\n", encoding="utf-8")
    result = trace.audit_trace(bogus)
    assert result.ok is False
    assert result.errors


def test_selfcheck_passes_when_no_traces(temp_harness: Path) -> None:
    runs = temp_harness / "runs"
    if runs.exists():
        for file in runs.glob("*.jsonl"):
            file.unlink()
    result = selfcheck._check_trace_chain()
    assert result.status is Status.PASS
    assert "nothing to audit" in result.summary


def test_selfcheck_fails_on_tampered_trace(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["specialist"] = "tampered"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = selfcheck._check_trace_chain()
    assert result.status is Status.FAIL


def test_cli_audit_intact(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    code = cli.main(["audit", str(path)])
    assert code == 0
    assert "OK" in capsys.readouterr().out


def test_cli_audit_detects_tampering(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_trace(temp_harness, monkeypatch)
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[1])
    record["specialist"] = "tampered"
    lines[1] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    code = cli.main(["audit", str(path), "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ok"] is False
