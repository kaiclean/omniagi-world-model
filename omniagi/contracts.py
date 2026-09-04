"""Typed tool contracts.

Every tool in the registry may declare a ``contract``: a typed description of
its inputs, outputs and the errors it raises. The contract is the machine-
readable half of the tool spec - it lets the orchestrator validate arguments
before a tool runs and lets ``omniagi check`` prove that no active tool ships
an untyped or malformed interface.

The check is deliberately graded:

* A **malformed** contract (missing sections, unknown field type, duplicate or
  unnamed field) is a hard failure - a broken contract is worse than none.
* A missing contract on an active tool is a **warning**, because the
  self-extension protocol legitimately registers a minimal tool first and the
  master fills in its contract as a follow-up.
"""

from __future__ import annotations

from typing import Any

from .registry import Registry, load_registry
from .results import CheckResult

VALID_TYPES = frozenset(
    {"string", "integer", "number", "boolean", "object", "array", "null"}
)


class ContractError(ValueError):
    """Raised when arguments do not satisfy a tool contract."""


def _validate_fields(where: str, fields: Any, errors: list[str]) -> None:
    if not isinstance(fields, list):
        errors.append(f"{where} must be a list")
        return
    seen: set[str] = set()
    for entry in fields:
        if not isinstance(entry, dict):
            errors.append(f"{where} entry is not an object")
            continue
        name = entry.get("name")
        if not name or not isinstance(name, str):
            errors.append(f"{where} entry is missing a name")
            continue
        if name in seen:
            errors.append(f"{where} has a duplicate field '{name}'")
        seen.add(name)
        field_type = entry.get("type")
        if field_type not in VALID_TYPES:
            errors.append(f"{where} field '{name}' has invalid type {field_type!r}")
        if not entry.get("description"):
            errors.append(f"{where} field '{name}' has no description")


def contract_errors(tool: dict[str, Any]) -> list[str]:
    """Return structural problems with a tool's contract (empty when valid)."""
    contract = tool.get("contract")
    errors: list[str] = []
    if contract is None:
        return errors
    tool_id = tool.get("id", "<unknown>")
    if not isinstance(contract, dict):
        return [f"tool '{tool_id}' contract is not an object"]
    if not contract.get("summary"):
        errors.append(f"tool '{tool_id}' contract has no summary")
    _validate_fields(f"tool '{tool_id}' inputs", contract.get("inputs", []), errors)
    _validate_fields(f"tool '{tool_id}' outputs", contract.get("outputs", []), errors)
    if not isinstance(contract.get("errors", []), list):
        errors.append(f"tool '{tool_id}' contract errors must be a list")
    return errors


def validate_arguments(tool: dict[str, Any], arguments: dict[str, Any]) -> None:
    """Validate ``arguments`` against a tool's input contract.

    Raises :class:`ContractError` when a required input is missing or an
    argument has the wrong JSON type. Tools without a contract accept anything.
    """
    contract = tool.get("contract")
    if not contract:
        return
    inputs = {field["name"]: field for field in contract.get("inputs", [])}
    for name, field in inputs.items():
        if field.get("required") and name not in arguments:
            raise ContractError(f"tool '{tool['id']}' requires input '{name}'")
    for name, value in arguments.items():
        field = inputs.get(name)
        if field is None:
            raise ContractError(f"tool '{tool['id']}' got unexpected input '{name}'")
        if not _type_matches(field["type"], value):
            raise ContractError(
                f"tool '{tool['id']}' input '{name}' must be {field['type']}, got {type(value).__name__}"
            )


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


def check_tool_contracts(registry: Registry | None = None) -> CheckResult:
    """Verify active tools carry a well-formed typed contract."""
    reg = registry or load_registry()
    name = "contracts.tool_contracts"
    errors: list[str] = []
    missing: list[str] = []
    typed = 0
    for tool in reg.tools:
        if tool.get("status") != "active":
            continue
        problems = contract_errors(tool)
        if problems:
            errors.extend(problems)
        elif tool.get("contract"):
            typed += 1
        else:
            missing.append(f"tool '{tool['id']}' has no typed contract")
    if errors:
        return CheckResult.failed(
            name, "one or more tool contracts are malformed", errors + missing
        )
    if missing:
        return CheckResult.warned(
            name, "some active tools have no typed contract yet", missing
        )
    return CheckResult.passed(name, f"all {typed} active tools declare a valid typed contract")
