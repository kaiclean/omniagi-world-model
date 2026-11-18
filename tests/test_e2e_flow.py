"""End-to-end test of the main flow: route -> seat call -> trace.

No network: ``urllib.request.urlopen`` is replaced, so the adapter's request
building and response parsing run for real while nothing leaves the process.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from omniagi import adapters
from omniagi.cli import main
from omniagi.routing import route
from omniagi.trace import Trace


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def test_route_then_seat_call_then_trace(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OMNIAGI_NO_TRACE", raising=False)
    monkeypatch.setenv(adapters.BASE_URL_VAR, "http://127.0.0.1:9/v1")
    monkeypatch.setenv("OMNIAGI_API_KEY", "test-key-not-a-secret")

    sent: dict = {}

    def fake_urlopen(request, timeout=None):  # type: ignore[no-untyped-def]
        sent["url"] = request.full_url
        sent["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps({"choices": [{"message": {"content": "done"}}]}).encode())

    monkeypatch.setattr(adapters.urllib.request, "urlopen", fake_urlopen)

    # 1. route through the CLI, which also records the trace for that command
    task = "fix the failing test in the parser"
    assert main(["route", task]) == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["task"] == task
    assert decision["seat"]
    assert decision == route(task).to_dict()

    # 2. call the chosen seat; the model name must be the routed engine
    response = adapters.call_seat(task, decision["seat"])
    assert response.content == "done"
    assert sent["url"].endswith("/v1/chat/completions")
    assert sent["payload"]["model"] == decision["engine"]
    assert sent["payload"]["messages"][-1]["content"] == task

    # 3. record the outcome in a trace and read it back from disk
    with Trace(command="e2e") as trace:
        trace.event("seat_call", seat=response.seat, engine=response.engine)
    records = [
        json.loads(line)
        for path in (temp_harness / "runs").glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    kinds = [(r["command"], r["kind"]) for r in records]
    assert ("route", "start") in kinds
    assert ("route", "result") in kinds
    assert ("route", "end") in kinds
    assert ("e2e", "seat_call") in kinds
    assert next(r for r in records if r["kind"] == "seat_call")["seat"] == decision["seat"]


def test_flow_without_credentials_reports_a_blocker_and_no_seat_call(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(adapters.BASE_URL_VAR, raising=False)
    monkeypatch.setattr(
        adapters.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network was used")
    )
    assert main(["route", "summarise this document"]) == 0
    seat = json.loads(capsys.readouterr().out)["seat"]
    with pytest.raises(adapters.SeatUnavailable):
        adapters.call_seat("summarise this document", seat)
