"""Provider-aware gateway resolution tests."""

from __future__ import annotations

import pytest

from omniagi import gateway


def test_cloud_seat_resolves_to_its_provider(registry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIAGI_BASE_URL", "https://gw.example/v1")
    monkeypatch.setenv("OMNIAGI_API_KEY", "k-not-a-secret")
    cloud = next(seat for seat in registry.seats if seat["tier"] == "cloud")
    endpoint = gateway.resolve_endpoint(cloud, registry)
    assert endpoint.provider_id == "gateway"
    assert endpoint.chat_url == "https://gw.example/v1/chat/completions"
    assert endpoint.has_credential
    assert endpoint.health_kind == "credential"


def test_local_seat_uses_provider_default_base_url(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OMNIAGI_LOCAL_BASE_URL", raising=False)
    local = next(seat for seat in registry.seats if seat["tier"] == "local")
    endpoint = gateway.resolve_endpoint(local, registry)
    assert endpoint.provider_id == "local"
    assert endpoint.health_kind == "endpoint"
    assert endpoint.base_url == "http://127.0.0.1:11434/v1"
    assert endpoint.api_key is None


def test_seat_without_provider_falls_back_to_legacy(
    registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIAGI_BASE_URL", "https://legacy.example/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-not-a-secret")
    seat = dict(registry.seats[0])
    seat.pop("provider", None)
    endpoint = gateway.resolve_endpoint(seat, registry)
    assert endpoint.provider_id == "(legacy)"
    assert endpoint.api_key_var == "OPENAI_API_KEY"
    assert endpoint.chat_url == "https://legacy.example/v1/chat/completions"


def test_credential_vars_uses_provider_declaration(registry) -> None:
    provider = registry.provider("gateway")
    assert gateway.credential_vars(provider) == tuple(provider["api_key_vars"])
    assert gateway.credential_vars(None) == gateway.LEGACY_API_KEY_VARS
