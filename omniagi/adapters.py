"""Reference engine-seat adapter.

This is the piece that connects the routing table to reality: a single seat
invoked end-to-end over an OpenAI-compatible chat-completions endpoint.

It is deliberately minimal and **env-keyed**. Without credentials it raises
:class:`SeatUnavailable` rather than returning placeholder text, because
fabricating a model response is exactly the failure mode the constitution
forbids. Tests that exercise it are skipped in CI for the same reason.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .gateway import LEGACY_API_KEY_VARS, LEGACY_BASE_URL_VAR, resolve_endpoint
from .health import select_available_seat
from .registry import Registry, load_registry

#: Kept for backward compatibility and tests; provider config now drives calls.
BASE_URL_VAR = LEGACY_BASE_URL_VAR
API_KEY_VARS = LEGACY_API_KEY_VARS
DEFAULT_TIMEOUT = 60.0

SYSTEM_PROMPT = (
    "You are OmniAGI operating under OmniAGI.md. You are the sole master of this "
    "world-model harness. Never claim a tool succeeded without real evidence."
)


class SeatUnavailable(RuntimeError):
    """Raised when no engine seat can actually be called."""


@dataclass(frozen=True)
class SeatResponse:
    seat: str
    engine: str
    content: str
    raw: dict[str, Any]


def call_seat(
    prompt: str,
    seat_id: str,
    registry: Registry | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> SeatResponse:
    """Call one engine seat. Raises rather than simulating."""
    reg = registry or load_registry()
    seat = reg.seat(seat_id)
    if seat is None:
        raise SeatUnavailable(f"unknown seat '{seat_id}'")

    endpoint = resolve_endpoint(seat, reg)
    if not endpoint.has_base_url or (
        endpoint.health_kind == "credential" and not endpoint.has_credential
    ):
        raise SeatUnavailable(
            f"seat '{seat_id}' is not callable: set {endpoint.base_url_var} and one of "
            + ", ".join(endpoint.api_key_vars)
        )

    payload = json.dumps(
        {
            "model": seat["engine"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if endpoint.api_key:
        headers["Authorization"] = "Bearer " + endpoint.api_key

    assert endpoint.chat_url is not None  # guaranteed by has_base_url above
    request = urllib.request.Request(  # noqa: S310 - scheme validated below
        url=endpoint.chat_url,
        data=payload,
        headers=headers,
        method="POST",
    )
    if request.type not in ("http", "https"):
        raise SeatUnavailable(f"refusing non-HTTP endpoint scheme: {request.type}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SeatUnavailable(f"seat '{seat_id}' call failed: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SeatUnavailable(f"seat '{seat_id}' returned an unexpected schema") from exc
    if not isinstance(content, str) or not content:
        raise SeatUnavailable(f"seat '{seat_id}' returned an unexpected schema (empty content)")

    return SeatResponse(seat=seat["id"], engine=seat["engine"], content=content, raw=body)


def call_with_fallback(
    prompt: str,
    preferred_seat: str,
    registry: Registry | None = None,
    probe_network: bool = False,
) -> SeatResponse:
    """Call ``preferred_seat``, falling back down the ladder, else raise."""
    reg = registry or load_registry()
    chosen = select_available_seat(preferred_seat, reg, probe_network=probe_network)
    if chosen is None:
        raise SeatUnavailable(
            "no engine seat is available - report a blocker; do NOT simulate model output"
        )
    return call_seat(prompt, chosen.seat_id, registry=reg)
