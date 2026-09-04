"""Typed world-state memory with provenance and conflict protection.

``MEMORY.md`` is the *narrative* durable memory - human-authored facts with
expiry. The world state is its *machine* counterpart: a typed key/value store
that the autonomous loop reads and writes as it observes the world.

Every fact is:

* **typed** - the recorded value must match its declared JSON type;
* **sourced** - it carries provenance (who observed it, in which run, when);
* **confidence-weighted** - a float in ``[0, 1]``;
* **conflict-protected** - asserting a *different* value for an existing key is a
  conflict. A lower-confidence assertion never silently overwrites a
  higher-confidence fact; the superseded value is retained in the fact's
  history so the resolution is auditable rather than lossy.

The store is a single JSON document written atomically under an advisory lock,
so concurrent observers cannot corrupt or race it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .paths import resolve
from .persistence import locked_json_update
from .results import CheckResult

WORLD_STATE_FILE = "memory/world-state.json"
VERSION = 1
VALID_TYPES = frozenset(
    {"string", "integer", "number", "boolean", "object", "array", "null"}
)


class WorldStateError(RuntimeError):
    """Raised when the world state is malformed or a fact is invalid."""


def _type_matches(expected: str, value: Any) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


@dataclass(frozen=True)
class Provenance:
    source: str
    observed_on: str
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"source": self.source, "observed_on": self.observed_on}
        if self.run_id is not None:
            data["run_id"] = self.run_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Provenance:
        return cls(
            source=data["source"],
            observed_on=data["observed_on"],
            run_id=data.get("run_id"),
        )


@dataclass
class Fact:
    key: str
    value: Any
    type: str
    confidence: float
    provenance: Provenance
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.type,
            "confidence": self.confidence,
            "provenance": self.provenance.to_dict(),
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fact:
        return cls(
            key=data["key"],
            value=data["value"],
            type=data["type"],
            confidence=float(data["confidence"]),
            provenance=Provenance.from_dict(data["provenance"]),
            history=list(data.get("history", [])),
        )


@dataclass(frozen=True)
class ConflictResolution:
    key: str
    kept: str  # "incoming" or "existing"
    reason: str


def _store_path(path: Path | None = None) -> Path:
    return path or resolve(WORLD_STATE_FILE)


def _empty() -> dict[str, Any]:
    return {"version": VERSION, "facts": {}}


def load_state(path: Path | None = None) -> dict[str, Any]:
    """Load the raw world-state document (empty when the file is absent)."""
    target = _store_path(path)
    if not target.exists():
        return _empty()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorldStateError(f"{target} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "facts" not in data:
        raise WorldStateError(f"{target} is not a valid world-state document")
    return data


def facts(path: Path | None = None) -> list[Fact]:
    """Return all recorded facts as typed objects."""
    state = load_state(path)
    return [Fact.from_dict(entry) for entry in state["facts"].values()]


def get_fact(key: str, path: Path | None = None) -> Fact | None:
    state = load_state(path)
    entry = state["facts"].get(key)
    return Fact.from_dict(entry) if entry is not None else None


def assert_fact(
    key: str,
    value: Any,
    value_type: str,
    source: str,
    confidence: float = 1.0,
    run_id: str | None = None,
    observed_on: date | None = None,
    path: Path | None = None,
) -> ConflictResolution:
    """Record an observation about the world, protecting against conflicts.

    Returns a :class:`ConflictResolution` describing whether the incoming value
    or the previously stored value won. The write is performed atomically under
    an advisory lock so concurrent observers cannot corrupt the store.
    """
    if value_type not in VALID_TYPES:
        raise WorldStateError(f"unknown value type {value_type!r}")
    if not _type_matches(value_type, value):
        raise WorldStateError(
            f"value for '{key}' does not match declared type '{value_type}'"
        )
    if not 0.0 <= confidence <= 1.0:
        raise WorldStateError("confidence must be in [0, 1]")

    provenance = Provenance(
        source=source,
        observed_on=(observed_on or date.today()).isoformat(),
        run_id=run_id,
    )
    target = _store_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    resolution_box: list[ConflictResolution] = []

    def _update(state: dict[str, Any] | None) -> dict[str, Any]:
        state = state or _empty()
        state.setdefault("version", VERSION)
        store = state.setdefault("facts", {})
        existing = store.get(key)
        new_fact = Fact(key, value, value_type, confidence, provenance)
        if existing is None:
            store[key] = new_fact.to_dict()
            resolution_box.append(ConflictResolution(key, "incoming", "new fact"))
            return state

        current = Fact.from_dict(existing)
        if current.value == value:
            # Same observation: refresh provenance, keep the higher confidence.
            new_fact.confidence = max(confidence, current.confidence)
            new_fact.history = current.history
            store[key] = new_fact.to_dict()
            resolution_box.append(ConflictResolution(key, "incoming", "confirmed existing value"))
            return state

        # A genuine conflict: the values disagree.
        if confidence > current.confidence:
            new_fact.history = [*current.history, _snapshot(current)]
            store[key] = new_fact.to_dict()
            resolution_box.append(
                ConflictResolution(key, "incoming", "higher confidence supersedes prior value")
            )
        else:
            current.history = [*current.history, _snapshot(new_fact)]
            store[key] = current.to_dict()
            resolution_box.append(
                ConflictResolution(
                    key, "existing", "kept higher-or-equal confidence prior value"
                )
            )
        return state

    locked_json_update(target, _update, default=_empty())
    return resolution_box[-1]


def _snapshot(fact: Fact) -> dict[str, Any]:
    return {
        "value": fact.value,
        "confidence": fact.confidence,
        "provenance": fact.provenance.to_dict(),
    }


def check_world_state(path: Path | None = None) -> CheckResult:
    """Verify the world state is well-typed, sourced and conflict-free."""
    name = "worldstate.consistency"
    target = _store_path(path)
    if not target.exists():
        return CheckResult.passed(name, "no world state recorded yet")
    try:
        state = load_state(target)
    except WorldStateError as exc:
        return CheckResult.failed(name, str(exc))

    errors: list[str] = []
    store = state.get("facts", {})
    if not isinstance(store, dict):
        return CheckResult.failed(name, "world-state 'facts' must be an object")

    for map_key, entry in store.items():
        try:
            fact = Fact.from_dict(entry)
        except (KeyError, TypeError) as exc:
            errors.append(f"fact '{map_key}' is malformed: {exc}")
            continue
        if fact.key != map_key:
            errors.append(f"fact '{map_key}' has mismatched key '{fact.key}'")
        if fact.type not in VALID_TYPES:
            errors.append(f"fact '{map_key}' has invalid type '{fact.type}'")
        elif not _type_matches(fact.type, fact.value):
            errors.append(f"fact '{map_key}' value does not match type '{fact.type}'")
        if not 0.0 <= fact.confidence <= 1.0:
            errors.append(f"fact '{map_key}' confidence {fact.confidence} out of range")
        if not fact.provenance.source:
            errors.append(f"fact '{map_key}' has no provenance source")

    if errors:
        return CheckResult.failed(name, "world state is inconsistent", errors)
    return CheckResult.passed(name, f"{len(store)} world-state facts are typed and sourced")
