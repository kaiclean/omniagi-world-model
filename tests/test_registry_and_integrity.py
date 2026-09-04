"""Registry, docgen and filesystem-reconciliation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import docgen, integrity
from omniagi.registry import (
    Registry,
    RegistryError,
    load_registry,
    registry_path,
    validate_registry,
)
from omniagi.results import Status


def _mutate(mutate) -> None:
    path = registry_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# -- registry ------------------------------------------------------------------


def test_registry_loads_and_is_self_consistent(registry: Registry) -> None:
    assert registry.master["role"] == "master"
    assert registry.tools and registry.agents and registry.seats


def test_every_agent_seat_exists(registry: Registry) -> None:
    seat_ids = {seat["id"] for seat in registry.seats}
    for agent in registry.agents:
        assert agent["default_seat"] in seat_ids


def test_unknown_seat_reference_is_rejected(registry: Registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["agents"][0]["default_seat"] = "no-such-seat"
    with pytest.raises(RegistryError, match="unknown seat"):
        validate_registry(data)


def test_duplicate_tool_ids_are_rejected(registry: Registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["tools"].append(dict(data["tools"][0]))
    with pytest.raises(RegistryError, match="duplicate tool ids"):
        validate_registry(data)


def test_duplicate_routing_priorities_are_rejected(registry: Registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["routing"]["rules"][1]["priority"] = data["routing"]["rules"][0]["priority"]
    with pytest.raises(RegistryError, match="priorities must be unique"):
        validate_registry(data)


def test_duplicate_seat_ranks_are_rejected(registry: Registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["seats"][1]["rank"] = data["seats"][0]["rank"]
    with pytest.raises(RegistryError, match="ranks must be unique"):
        validate_registry(data)


def test_unknown_escalation_seat_is_rejected(registry: Registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["escalation"]["ladder"].append("imaginary-seat")
    with pytest.raises(RegistryError, match="escalation ladder"):
        validate_registry(data)


def test_missing_registry_raises(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="registry not found"):
        load_registry(tmp_path / "nope.json")


def test_escalation_ladder_is_ordered_by_cost(registry: Registry) -> None:
    """A ladder that does not get more expensive is not an escalation ladder."""
    costs = [registry.seat(sid)["relative_cost"] for sid in registry.escalation["ladder"]]
    assert costs == sorted(costs), f"ladder costs are not ascending: {costs}"


def test_every_link_exemption_has_a_reason(registry: Registry) -> None:
    for item in registry.data["link_exemptions"]:
        assert len(item["reason"]) > 10, f"undocumented exemption: {item['path']}"


# -- docgen --------------------------------------------------------------------


def test_generated_docs_are_up_to_date() -> None:
    assert docgen.generate(check_only=True) == []


def test_docgen_is_idempotent(temp_harness: Path) -> None:
    docgen.generate()
    assert docgen.generate() == []


def test_registry_change_makes_docs_stale(temp_harness: Path) -> None:
    _mutate(lambda data: data["tools"].append(
        {
            "id": "brand_new",
            "name": "Brand new",
            "spec": "tools/file_read.md",
            "status": "active",
            "script": None,
            "handler": None,
            "notes": "temporary",
        }
    ))
    stale = docgen.generate(check_only=True)
    assert "TOOLS.md" in stale
    result = docgen.check_docs()
    assert result.status is Status.FAIL


def test_hand_edited_generated_block_is_detected(temp_harness: Path) -> None:
    tools = temp_harness / "TOOLS.md"
    text = tools.read_text(encoding="utf-8").replace("| `file_read` |", "| `hand_edited` |")
    tools.write_text(text, encoding="utf-8")
    assert "TOOLS.md" in docgen.generate(check_only=True)


def test_missing_marker_is_reported(temp_harness: Path) -> None:
    tools = temp_harness / "TOOLS.md"
    tools.write_text("# TOOLS.md\nno markers here\n", encoding="utf-8")
    result = docgen.check_docs()
    assert result.status is Status.FAIL
    assert "missing generated block" in result.summary


def test_every_generated_target_exists(registry: Registry) -> None:
    from omniagi.paths import resolve

    for rel_path in docgen.BLOCKS:
        assert resolve(rel_path).is_file(), rel_path


# -- integrity -----------------------------------------------------------------


def test_all_integrity_checks_pass() -> None:
    for result in integrity.all_checks():
        assert result.status is Status.PASS, f"{result.name}: {result.details}"


def test_unregistered_tool_spec_is_detected(temp_harness: Path) -> None:
    (temp_harness / "tools" / "orphan.md").write_text("# Tool: orphan\n", encoding="utf-8")
    result = integrity.check_tool_specs()
    assert result.status is Status.FAIL
    assert any("unregistered tool spec" in d for d in result.details)


def test_registered_tool_without_a_spec_is_detected(temp_harness: Path) -> None:
    (temp_harness / "tools" / "file_read.md").unlink()
    result = integrity.check_tool_specs()
    assert result.status is Status.FAIL
    assert any("missing spec" in d for d in result.details)


def test_missing_tool_script_is_detected(temp_harness: Path) -> None:
    (temp_harness / "omniagi" / "shell.py").unlink()
    result = integrity.check_scripts()
    assert result.status is Status.FAIL
    assert any("missing script" in d for d in result.details)


def test_broken_markdown_link_is_detected(temp_harness: Path) -> None:
    (temp_harness / "tools" / "file_read.md").write_text(
        "# Tool: file_read\nSee [nowhere](does/not/exist.md).\n", encoding="utf-8"
    )
    result = integrity.check_markdown_links()
    assert result.status is Status.FAIL
    assert any("does/not/exist.md" in d for d in result.details)


def test_hardcoded_host_path_is_detected(temp_harness: Path) -> None:
    """Regression guard for the original macOS-only paths."""
    offending = "/Users/" + "somebody/research/omniagi-world-model"
    (temp_harness / "omniagi" / "legacy.py").write_text(
        f'ROOT = "{offending}"\n', encoding="utf-8"
    )
    result = integrity.check_no_hardcoded_paths()
    assert result.status is Status.FAIL
    assert any("legacy.py" in d for d in result.details)


def test_no_module_hardcodes_a_host_path() -> None:
    assert integrity.check_no_hardcoded_paths().status is Status.PASS


def test_missing_constitution_file_is_detected(temp_harness: Path) -> None:
    (temp_harness / "MEMORY.md").unlink()
    result = integrity.check_constitution_files()
    assert result.status is Status.FAIL
