"""Provider-aware gateway resolution.

Seats are served by *providers* (declared in ``registry/harness.json``). A
provider says where its OpenAI-compatible endpoint lives (which environment
variable holds the base URL, and a default), which environment variables may
hold an API key, the chat-completions path to append, and how the provider's
health is established (a credential must be present, or a local endpoint must
answer).

Centralising that here keeps :mod:`omniagi.adapters` and :mod:`omniagi.health`
from each growing their own copy of the provider rules, and means a new provider
is added by editing the registry rather than the code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .registry import Registry

#: Legacy environment variables used when a seat declares no provider. These
#: preserve the pre-provider behaviour so an older registry still resolves.
LEGACY_BASE_URL_VAR = "OMNIAGI_BASE_URL"
LEGACY_API_KEY_VARS = (
    "OMNIAGI_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPINFRA_API_KEY",
    "TOGETHER_API_KEY",
)
DEFAULT_CHAT_PATH = "/chat/completions"


@dataclass(frozen=True)
class Endpoint:
    """A fully-resolved call target for one seat."""

    provider_id: str
    tier: str
    health_kind: str  # "credential" | "endpoint"
    base_url: str | None
    chat_url: str | None
    api_key: str | None
    api_key_var: str | None
    base_url_var: str
    api_key_vars: tuple[str, ...]

    @property
    def has_base_url(self) -> bool:
        return bool(self.base_url)

    @property
    def has_credential(self) -> bool:
        return bool(self.api_key)


def provider_for_seat(seat: dict[str, Any], registry: Registry) -> dict[str, Any] | None:
    """Return the provider record a seat is served by, or ``None`` if legacy."""
    provider_id = seat.get("provider")
    if not provider_id:
        return None
    return registry.provider(provider_id)


def _first_present(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


def credential_vars(provider: dict[str, Any] | None) -> tuple[str, ...]:
    """Environment variables that may hold this provider's API key."""
    if provider is None:
        return LEGACY_API_KEY_VARS
    return tuple(provider.get("api_key_vars", ()))


def resolve_endpoint(seat: dict[str, Any], registry: Registry) -> Endpoint:
    """Resolve the concrete endpoint for ``seat`` from the environment."""
    provider = provider_for_seat(seat, registry)
    if provider is None:
        base = os.environ.get(LEGACY_BASE_URL_VAR)
        key, key_var = _first_present(LEGACY_API_KEY_VARS)
        chat = base.rstrip("/") + DEFAULT_CHAT_PATH if base else None
        return Endpoint(
            provider_id="(legacy)",
            tier=seat.get("tier", "cloud"),
            health_kind="credential",
            base_url=base,
            chat_url=chat,
            api_key=key,
            api_key_var=key_var,
            base_url_var=LEGACY_BASE_URL_VAR,
            api_key_vars=LEGACY_API_KEY_VARS,
        )

    base_url_var = provider["base_url_var"]
    base = os.environ.get(base_url_var) or provider.get("base_url_default")
    key_vars = tuple(provider.get("api_key_vars", ()))
    key, key_var = _first_present(key_vars)
    chat_path = provider.get("chat_path", DEFAULT_CHAT_PATH)
    chat = base.rstrip("/") + chat_path if base else None
    return Endpoint(
        provider_id=provider["id"],
        tier=provider["tier"],
        health_kind=provider["health"],
        base_url=base,
        chat_url=chat,
        api_key=key,
        api_key_var=key_var,
        base_url_var=base_url_var,
        api_key_vars=key_vars,
    )
