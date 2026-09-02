"""Canonical harness registry.

``registry/harness.json`` is the single source of truth for the master, the
specialist subroutines, the tool registry, the engine seats and the routing
rules.  Every markdown table describing any of those is generated from here, so
the three-way drift between prose, references and code cannot recur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import resolve

REGISTRY_PATH = ("registry", "harness.json")
SCHEMA_PATH = ("registry", "schema.json")


class RegistryError(RuntimeError):
    """Raised when the registry is missing, malformed or schema-invalid."""


@dataclass(frozen=True)
class Registry:
    """An immutable view over the parsed registry document."""

    data: dict[str, Any]
    path: Path = field(compare=False)

    # -- convenience accessors -------------------------------------------------
    @property
    def master(self) -> dict[str, Any]:
        return self.data["master"]

    @property
    def agents(self) -> list[dict[str, Any]]:
        return self.data["agents"]

    @property
    def tools(self) -> list[dict[str, Any]]:
        return self.data["tools"]

    @property
    def seats(self) -> list[dict[str, Any]]:
        return self.data["seats"]

    @property
    def routing(self) -> dict[str, Any]:
        return self.data["routing"]

    @property
    def escalation(self) -> dict[str, Any]:
        return self.data["escalation"]

    @property
    def non_negotiables(self) -> list[dict[str, Any]]:
        return self.data["non_negotiables"]

    @property
    def constitution_files(self) -> list[str]:
        return self.data["constitution_files"]

    @property
    def max_evidence_age_days(self) -> int:
        return int(self.data["freshness"]["max_evidence_age_days"])

    def seat(self, seat_id: str) -> dict[str, Any] | None:
        for seat in self.seats:
            if seat["id"] == seat_id:
                return seat
        return None

    def agent(self, agent_id: str) -> dict[str, Any] | None:
        for agent in self.agents:
            if agent["id"] == agent_id:
                return agent
        return None

    def tool(self, tool_id: str) -> dict[str, Any] | None:
        for tool in self.tools:
            if tool["id"] == tool_id:
                return tool
        return None


def registry_path() -> Path:
    return resolve(*REGISTRY_PATH)


def schema_path() -> Path:
    return resolve(*SCHEMA_PATH)


def load_registry(path: Path | None = None) -> Registry:
    """Load and structurally validate the registry."""
    target = path or registry_path()
    if not target.exists():
        raise RegistryError(f"registry not found: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RegistryError(f"registry is not valid JSON: {exc}") from exc
    validate_registry(data)
    return Registry(data=data, path=target)


@lru_cache(maxsize=1)
def _cached_schema(schema_file: str) -> dict[str, Any]:
    return json.loads(Path(schema_file).read_text(encoding="utf-8"))


def validate_registry(data: dict[str, Any], schema_file: Path | None = None) -> None:
    """Validate the registry against the JSON Schema plus referential rules.

    ``jsonschema`` is an optional dependency: when it is unavailable the
    schema step is skipped, but the referential-integrity rules below always
    run so the registry can never silently reference a non-existent seat.
    """
    schema_target = schema_file or schema_path()
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        if schema_target.exists():
            schema = _cached_schema(str(schema_target))
            try:
                jsonschema.validate(instance=data, schema=schema)
            except jsonschema.ValidationError as exc:
                location = "/".join(str(p) for p in exc.absolute_path)
                raise RegistryError(
                    f"registry failed schema validation at '{location or '<root>'}': {exc.message}"
                ) from exc

    _validate_references(data)


def _validate_references(data: dict[str, Any]) -> None:
    errors: list[str] = []

    for key in ("master", "agents", "tools", "seats", "routing", "escalation"):
        if key not in data:
            errors.append(f"registry is missing required key '{key}'")
    if errors:
        raise RegistryError("; ".join(errors))

    seat_ids = {seat["id"] for seat in data["seats"]}
    agent_ids = {agent["id"] for agent in data["agents"]}

    if len(seat_ids) != len(data["seats"]):
        errors.append("duplicate seat ids in registry")
    if len(agent_ids) != len(data["agents"]):
        errors.append("duplicate agent ids in registry")

    tool_ids = [tool["id"] for tool in data["tools"]]
    if len(set(tool_ids)) != len(tool_ids):
        errors.append("duplicate tool ids in registry")

    for agent in data["agents"]:
        if agent["default_seat"] not in seat_ids:
            errors.append(
                f"agent '{agent['id']}' references unknown seat '{agent['default_seat']}'"
            )

    routing = data["routing"]
    for rule in routing["rules"]:
        if rule["seat"] not in seat_ids:
            errors.append(
                f"routing rule '{rule['specialist']}' references unknown seat '{rule['seat']}'"
            )
        if rule["specialist"] not in agent_ids:
            errors.append(f"routing rule references unknown specialist '{rule['specialist']}'")

    default = routing["default"]
    if default["seat"] not in seat_ids:
        errors.append(f"default route references unknown seat '{default['seat']}'")
    if default["specialist"] not in agent_ids:
        errors.append(f"default route references unknown specialist '{default['specialist']}'")

    priorities = [rule["priority"] for rule in routing["rules"]]
    if len(set(priorities)) != len(priorities):
        errors.append("routing rule priorities must be unique so tie-breaks are deterministic")

    for seat_id in data["escalation"]["ladder"]:
        if seat_id not in seat_ids:
            errors.append(f"escalation ladder references unknown seat '{seat_id}'")

    ranks = [seat["rank"] for seat in data["seats"]]
    if len(set(ranks)) != len(ranks):
        errors.append("seat ranks must be unique")

    if errors:
        raise RegistryError("; ".join(errors))
