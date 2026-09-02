"""Reference adapter tests.

The adapter is the only place the harness talks to a real model, so "it is hard
to test" is not an acceptable reason to leave it unexercised — that is exactly
the code path where fabricating a response would do the most damage.

These tests run the *full* request/response cycle against a stub
OpenAI-compatible server on localhost. Nothing is mocked out of the adapter
itself, so the URL construction, headers, payload shape and error handling are
all genuinely executed. A live test against a real seat is available opt-in via
``OMNIAGI_LIVE_SEAT_TEST=1``.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from omniagi import adapters, health

LIVE_TEST_VAR = "OMNIAGI_LIVE_SEAT_TEST"


class _StubHandler(BaseHTTPRequestHandler):
    """Minimal OpenAI-compatible chat-completions endpoint."""

    status = 200
    body: dict | str = {"choices": [{"message": {"content": "stub reply"}}]}
    captured: dict = {}

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        type(self).captured = {
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "content_type": self.headers.get("Content-Type", ""),
            "payload": json.loads(raw),
        }
        payload = self.body if isinstance(self.body, str) else json.dumps(self.body)
        encoded = payload.encode("utf-8")
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args: object) -> None:
        """Silence the default stderr access log."""


@pytest.fixture
def stub_seat(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_StubHandler]]:
    _StubHandler.status = 200
    _StubHandler.body = {"choices": [{"message": {"content": "stub reply"}}]}
    _StubHandler.captured = {}

    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]

    monkeypatch.setenv(adapters.BASE_URL_VAR, f"http://{host}:{port}/v1")
    monkeypatch.setenv("OMNIAGI_API_KEY", "test-key-not-a-secret")
    try:
        yield _StubHandler
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_end_to_end_call_returns_the_model_content(stub_seat, registry) -> None:
    seat_id = registry.seats[0]["id"]
    response = adapters.call_seat("say hello", seat_id)

    assert response.content == "stub reply"
    assert response.seat == seat_id
    assert response.engine == registry.seat(seat_id)["engine"]
    assert response.raw["choices"][0]["message"]["content"] == "stub reply"


def test_request_shape_matches_the_openai_contract(stub_seat, registry) -> None:
    seat_id = registry.seats[0]["id"]
    adapters.call_seat("say hello", seat_id)
    captured = stub_seat.captured

    assert captured["path"] == "/v1/chat/completions"
    assert captured["content_type"] == "application/json"
    assert captured["payload"]["model"] == registry.seat(seat_id)["engine"]
    roles = [message["role"] for message in captured["payload"]["messages"]]
    assert roles == ["system", "user"]
    assert captured["payload"]["messages"][1]["content"] == "say hello"


def test_the_system_prompt_asserts_single_mastership(stub_seat, registry) -> None:
    """The constitution must reach the model, not just the repository."""
    adapters.call_seat("say hello", registry.seats[0]["id"])
    system = stub_seat.captured["payload"]["messages"][0]["content"]
    assert "sole master" in system
    assert "Never claim a tool succeeded" in system


def test_the_api_key_is_sent_as_a_bearer_token(stub_seat, registry) -> None:
    adapters.call_seat("say hello", registry.seats[0]["id"])
    assert stub_seat.captured["authorization"] == "Bearer " + os.environ["OMNIAGI_API_KEY"]


def test_trailing_slash_in_the_base_url_is_normalised(
    stub_seat, registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapters.BASE_URL_VAR, os.environ[adapters.BASE_URL_VAR] + "/")
    adapters.call_seat("say hello", registry.seats[0]["id"])
    assert stub_seat.captured["path"] == "/v1/chat/completions"


def test_fallback_reaches_a_reachable_seat(stub_seat, registry) -> None:
    """cloud down -> fall back is an executed decision, not documented intent."""
    local = next(seat for seat in registry.seats if seat["tier"] == "local")
    response = adapters.call_with_fallback("say hello", preferred_seat=local["id"])
    assert response.seat != local["id"]
    assert response.content == "stub reply"


# -- refusals ------------------------------------------------------------------


def test_missing_credentials_raise_rather_than_fabricate(
    monkeypatch: pytest.MonkeyPatch, registry
) -> None:
    monkeypatch.delenv(adapters.BASE_URL_VAR, raising=False)
    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(adapters.SeatUnavailable) as excinfo:
        adapters.call_seat("say hello", registry.seats[0]["id"])
    assert adapters.BASE_URL_VAR in str(excinfo.value)


def test_unknown_seat_is_refused(stub_seat) -> None:
    with pytest.raises(adapters.SeatUnavailable) as excinfo:
        adapters.call_seat("say hello", "no_such_seat")
    assert "unknown seat" in str(excinfo.value)


@pytest.mark.parametrize("scheme", ["file:///etc/passwd", "ftp://example.com/v1"])
def test_non_http_endpoints_are_refused(
    scheme: str, monkeypatch: pytest.MonkeyPatch, registry
) -> None:
    """A hostile OMNIAGI_BASE_URL must not turn the adapter into a file reader."""
    monkeypatch.setenv(adapters.BASE_URL_VAR, scheme)
    monkeypatch.setenv("OMNIAGI_API_KEY", "test-key-not-a-secret")
    with pytest.raises(adapters.SeatUnavailable):
        adapters.call_seat("say hello", registry.seats[0]["id"])


def test_server_error_is_reported_as_unavailable(stub_seat, registry) -> None:
    stub_seat.status = 500
    with pytest.raises(adapters.SeatUnavailable) as excinfo:
        adapters.call_seat("say hello", registry.seats[0]["id"])
    assert "call failed" in str(excinfo.value)


def test_non_json_response_is_refused(stub_seat, registry) -> None:
    stub_seat.body = "<html>gateway error</html>"
    with pytest.raises(adapters.SeatUnavailable):
        adapters.call_seat("say hello", registry.seats[0]["id"])


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{}]},
        {"error": {"message": "quota exceeded"}},
        {"choices": [{"message": {}}]},
    ],
)
def test_unexpected_schema_is_refused_never_coerced(stub_seat, registry, body: dict) -> None:
    """An empty or malformed reply must raise, not become an empty answer."""
    stub_seat.body = body
    with pytest.raises(adapters.SeatUnavailable) as excinfo:
        adapters.call_seat("say hello", registry.seats[0]["id"])
    assert "unexpected schema" in str(excinfo.value)


# -- opt-in live check ---------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get(LIVE_TEST_VAR) != "1",
    reason=f"live seat call is opt-in; set {LIVE_TEST_VAR}=1 with real credentials",
)
def test_live_seat_call(registry) -> None:  # pragma: no cover - opt-in only
    seat = health.select_available_seat(registry.escalation["ladder"][0], registry)
    if seat is None:
        pytest.skip("no engine seat is reachable")
    response = adapters.call_seat("Reply with the single word: ready.", seat.seat_id)
    assert response.content.strip()
