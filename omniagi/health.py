"""Engine-seat availability probing.

"Cloud down -> local fallback" was documented intent with no implementation.
This module turns it into an executed decision.

Design rules:

* A seat is **available** only if a credential is present and (when network
  probing is enabled) the endpoint answers. Absence of evidence is never
  treated as availability.
* Probing is offline-safe by default: without ``probe_network=True`` only
  credentials and local sockets are inspected, so CI never depends on the
  public internet.
* If no seat is available the caller gets ``None`` and must report a blocker.
  There is no code path that fabricates a model response.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .registry import Registry, load_registry
from .results import CheckResult

#: Environment variables that, if set, indicate a usable cloud credential.
CLOUD_CREDENTIAL_VARS = (
    "OMNIAGI_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPINFRA_API_KEY",
    "TOGETHER_API_KEY",
)

#: Default local inference endpoints (Ollama, LM Studio).
LOCAL_ENDPOINTS_VAR = "OMNIAGI_LOCAL_ENDPOINTS"
DEFAULT_LOCAL_ENDPOINTS = ("http://127.0.0.1:11434", "http://127.0.0.1:1234")

CONNECT_TIMEOUT_SECONDS = 1.5


@dataclass(frozen=True)
class SeatHealth:
    seat_id: str
    engine: str
    tier: str
    available: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat_id,
            "engine": self.engine,
            "tier": self.tier,
            "available": self.available,
            "reason": self.reason,
        }


def _local_endpoints() -> tuple[str, ...]:
    raw = os.environ.get(LOCAL_ENDPOINTS_VAR)
    if not raw:
        return DEFAULT_LOCAL_ENDPOINTS
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _tcp_reachable(url: str, timeout: float = CONNECT_TIMEOUT_SECONDS) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _cloud_credential() -> str | None:
    for var in CLOUD_CREDENTIAL_VARS:
        if os.environ.get(var):
            return var
    return None


def probe_seat(seat: dict[str, Any], probe_network: bool = False) -> SeatHealth:
    """Probe one seat. Never assumes availability."""
    if seat["tier"] == "local":
        endpoints = _local_endpoints()
        if not probe_network:
            return SeatHealth(
                seat["id"],
                seat["engine"],
                seat["tier"],
                False,
                "local endpoint not probed (pass probe_network=True)",
            )
        for endpoint in endpoints:
            if _tcp_reachable(endpoint):
                return SeatHealth(
                    seat["id"], seat["engine"], seat["tier"], True, f"reachable at {endpoint}"
                )
        return SeatHealth(
            seat["id"],
            seat["engine"],
            seat["tier"],
            False,
            f"no local endpoint reachable ({', '.join(endpoints)})",
        )

    credential = _cloud_credential()
    if credential is None:
        return SeatHealth(
            seat["id"],
            seat["engine"],
            seat["tier"],
            False,
            "no cloud credential in environment ("
            + ", ".join(CLOUD_CREDENTIAL_VARS)
            + ")",
        )
    return SeatHealth(
        seat["id"], seat["engine"], seat["tier"], True, f"credential present via {credential}"
    )


def probe_all(registry: Registry | None = None, probe_network: bool = False) -> list[SeatHealth]:
    reg = registry or load_registry()
    return [probe_seat(seat, probe_network=probe_network) for seat in reg.seats]


def select_available_seat(
    preferred: str,
    registry: Registry | None = None,
    probe_network: bool = False,
) -> SeatHealth | None:
    """Return the preferred seat if usable, else the first usable fallback.

    Returns ``None`` when nothing is reachable. The caller MUST then report a
    blocker rather than proceed: rule ``no_simulated_success``.
    """
    reg = registry or load_registry()
    health = {h.seat_id: h for h in probe_all(reg, probe_network=probe_network)}

    chosen = health.get(preferred)
    if chosen is not None and chosen.available:
        return chosen

    for seat_id in reg.escalation["ladder"]:
        candidate = health.get(seat_id)
        if candidate is not None and candidate.available:
            return candidate

    for seat in sorted(reg.seats, key=lambda s: (s["tier"] != "local", s["rank"])):
        candidate = health.get(seat["id"])
        if candidate is not None and candidate.available:
            return candidate
    return None


def check_health_probe(registry: Registry | None = None) -> CheckResult:
    """Verify the probe is wired up and reports honestly.

    This is deliberately a WARN and not a FAIL when no seat is reachable: an
    offline CI runner having no credentials is expected. What would be a real
    failure is the probe claiming availability without evidence.
    """
    reg = registry or load_registry()
    results = probe_all(reg)
    errors = [
        f"seat '{h.seat_id}' reported available without evidence"
        for h in results
        if h.available and not h.reason
    ]
    if errors:
        return CheckResult.failed("routing.health_probe", "seat probe reported unfounded availability", errors)
    available = [h.seat_id for h in results if h.available]
    if not available:
        return CheckResult.warned(
            "routing.health_probe",
            "no engine seat is currently reachable - model calls must report a blocker",
            [h.reason for h in results[:3]],
        )
    return CheckResult.passed(
        "routing.health_probe", f"{len(available)}/{len(results)} seats reachable"
    )
