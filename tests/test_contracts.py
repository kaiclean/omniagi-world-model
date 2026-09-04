"""Typed tool-contract tests."""

from __future__ import annotations

import copy

import pytest

from omniagi import contracts
from omniagi.results import Status


def test_committed_contracts_pass(registry) -> None:
    result = contracts.check_tool_contracts(registry)
    assert result.status is Status.PASS
    assert "12" in result.summary


def test_missing_contract_is_a_warning(registry) -> None:
    reg = copy.deepcopy(registry)
    reg.tools[0].pop("contract", None)
    result = contracts.check_tool_contracts(reg)
    assert result.status is Status.WARN
    assert any("no typed contract" in detail for detail in result.details)


def test_inactive_tool_without_contract_is_ignored(registry) -> None:
    reg = copy.deepcopy(registry)
    reg.tools[0]["status"] = "retired"
    reg.tools[0].pop("contract", None)
    result = contracts.check_tool_contracts(reg)
    assert result.status is Status.PASS


def test_unknown_field_type_fails(registry) -> None:
    reg = copy.deepcopy(registry)
    reg.tools[0]["contract"]["inputs"][0]["type"] = "bogus"
    result = contracts.check_tool_contracts(reg)
    assert result.status is Status.FAIL
    assert any("invalid type" in detail for detail in result.details)


def test_duplicate_field_fails(registry) -> None:
    reg = copy.deepcopy(registry)
    first = reg.tools[0]["contract"]["inputs"][0]
    reg.tools[0]["contract"]["inputs"].append(dict(first))
    result = contracts.check_tool_contracts(reg)
    assert result.status is Status.FAIL
    assert any("duplicate field" in detail for detail in result.details)


def test_validate_arguments_accepts_valid_payload(registry) -> None:
    tool = next(t for t in registry.tools if t["id"] == "file_write")
    contracts.validate_arguments(tool, {"path": "MEMORY.md", "content": "hi"})


def test_validate_arguments_rejects_missing_required(registry) -> None:
    tool = next(t for t in registry.tools if t["id"] == "file_write")
    with pytest.raises(contracts.ContractError, match="requires input 'content'"):
        contracts.validate_arguments(tool, {"path": "MEMORY.md"})


def test_validate_arguments_rejects_wrong_type(registry) -> None:
    tool = next(t for t in registry.tools if t["id"] == "file_write")
    with pytest.raises(contracts.ContractError, match="must be string"):
        contracts.validate_arguments(tool, {"path": "MEMORY.md", "content": 5})


def test_validate_arguments_rejects_unexpected_input(registry) -> None:
    tool = next(t for t in registry.tools if t["id"] == "file_read")
    with pytest.raises(contracts.ContractError, match="unexpected input"):
        contracts.validate_arguments(tool, {"path": "MEMORY.md", "mode": "r"})


def test_bool_is_not_integer(registry) -> None:
    tool = next(t for t in registry.tools if t["id"] == "shell")
    with pytest.raises(contracts.ContractError, match="must be number"):
        contracts.validate_arguments(tool, {"argv": ["ls"], "timeout": True})
