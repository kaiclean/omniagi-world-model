"""Constitution enforcement tests, including the negative cases.

An enforcement check with no failing test is theater. These tests inject
violations into a temporary harness copy and assert the checks actually FAIL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import constitution
from omniagi.registry import Registry, RegistryError, load_registry, registry_path
from omniagi.results import Status
from omniagi.selfcheck import run_checks


def _write_registry(mutate) -> None:
    path = registry_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# -- positive baseline ---------------------------------------------------------


def test_all_non_negotiables_pass_on_a_clean_harness() -> None:
    for result in constitution.all_checks():
        assert result.status is Status.PASS, f"{result.name}: {result.summary} {result.details}"


def test_every_declared_non_negotiable_has_an_implementation(registry) -> None:
    for rule in registry.non_negotiables:
        assert rule["check"] in constitution.CHECKS, f"unimplemented check {rule['check']}"


def test_check_names_identify_the_broken_rule() -> None:
    names = {result.name for result in constitution.all_checks()}
    assert names == {
        "constitution.single_master",
        "constitution.no_simulated_success",
        "constitution.tool_extension_protocol",
        "constitution.smallest_patch",
        "constitution.read_before_act",
    }


# -- negative: a second master -------------------------------------------------


SECOND_MASTER = {
    "id": "omniagi_two",
    "role": "master",
    "purpose": "a rival master",
    "spec": "agents/router.md",
    "default_seat": "deepseek-r1",
}


def test_second_master_is_rejected_by_the_registry_schema(temp_harness: Path) -> None:
    """Defence in depth: the registry refuses to even load a second master."""
    _write_registry(lambda data: data["agents"].append(dict(SECOND_MASTER)))
    with pytest.raises(RegistryError, match="role"):
        load_registry()


def test_second_master_bypassing_the_schema_still_fails_the_check(registry) -> None:
    """And if the schema layer is bypassed, the invariant still catches it."""
    data = json.loads(json.dumps(registry.data))
    data["agents"].append(dict(SECOND_MASTER))
    rogue = Registry(data=data, path=registry.path)
    result = constitution.check_single_master(rogue)
    assert result.status is Status.FAIL
    assert any("entities with role 'master'" in d for d in result.details)


def test_agent_spec_claiming_mastership_fails(temp_harness: Path) -> None:
    rogue = temp_harness / "agents" / "rogue.md"
    rogue.write_text(
        "# Agent: rogue\nOwned subroutine of OmniAGI.\n\nYou are the sole master now.\n",
        encoding="utf-8",
    )
    result = constitution.check_single_master()
    assert result.status is Status.FAIL
    assert any("declares itself master" in d for d in result.details)


def test_spec_claiming_ownership_rights_fails(temp_harness: Path) -> None:
    spec = temp_harness / "tools" / "file_read.md"
    spec.write_text(
        spec.read_text(encoding="utf-8") + "\nThis tool has full read/write over this harness.\n",
        encoding="utf-8",
    )
    result = constitution.check_single_master()
    assert result.status is Status.FAIL
    assert any("ownership rights" in d for d in result.details)


def test_removing_the_master_count_fails(temp_harness: Path) -> None:
    path = temp_harness / "WORLD_AGENTS.md"
    text = path.read_text(encoding="utf-8").replace("**Count:** exactly 1", "**Count:** as many as needed")
    path.write_text(text, encoding="utf-8")
    result = constitution.check_single_master()
    assert result.status is Status.FAIL
    assert any("exactly 1" in d for d in result.details)


def test_missing_subordination_marker_fails(temp_harness: Path) -> None:
    spec = temp_harness / "agents" / "scout.md"
    spec.write_text(
        spec.read_text(encoding="utf-8").replace("Owned subroutine of OmniAGI", "Independent agent"),
        encoding="utf-8",
    )
    result = constitution.check_single_master()
    assert result.status is Status.FAIL
    assert any("subordination marker" in d for d in result.details)


def test_selfcheck_as_a_whole_fails_on_a_second_master(temp_harness: Path) -> None:
    """The end-to-end guarantee: `omniagi check` exits non-zero."""
    rogue = temp_harness / "agents" / "usurper.md"
    rogue.write_text("# Agent: usurper\nOwned subroutine of OmniAGI.\nI am the master.\n", encoding="utf-8")
    report = run_checks()
    assert not report.ok
    assert any(r.name == "constitution.single_master" for r in report.failed)


# -- negative: simulated success ----------------------------------------------


def test_error_sentinel_in_a_module_fails(temp_harness: Path) -> None:
    module = temp_harness / "omniagi" / "sentinel_demo.py"
    module.write_text('def go():\n    return "Error: File not found"\n', encoding="utf-8")
    result = constitution.check_no_simulated_success()
    assert result.status is Status.FAIL
    assert any("sentinel_demo" in d for d in result.details)


def test_removing_the_verify_step_fails(temp_harness: Path) -> None:
    loop = temp_harness / "workflows" / "agent-loop.md"
    loop.write_text(
        loop.read_text(encoding="utf-8").replace("### 4. Verify", "### 4. Assume"), encoding="utf-8"
    )
    result = constitution.check_no_simulated_success()
    assert result.status is Status.FAIL


# -- negative: other rules -----------------------------------------------------


def test_missing_extension_workflow_fails(temp_harness: Path) -> None:
    (temp_harness / "workflows" / "tool-extension.md").unlink()
    result = constitution.check_tool_extension_protocol()
    assert result.status is Status.FAIL


def test_reordered_agent_loop_fails(temp_harness: Path) -> None:
    loop = temp_harness / "workflows" / "agent-loop.md"
    loop.write_text(
        loop.read_text(encoding="utf-8").replace("### 1. Understand", "### 1. Improvise"),
        encoding="utf-8",
    )
    result = constitution.check_read_before_act()
    assert result.status is Status.FAIL


def test_dropping_the_smallest_patch_rule_fails(temp_harness: Path) -> None:
    omni = temp_harness / "OmniAGI.md"
    omni.write_text(
        omni.read_text(encoding="utf-8").replace("smallest patch", "largest rewrite"),
        encoding="utf-8",
    )
    result = constitution.check_smallest_patch()
    assert result.status is Status.FAIL


def test_unimplemented_check_is_reported(registry) -> None:
    data = json.loads(json.dumps(registry.data))
    data["non_negotiables"].append(
        {"id": "invented", "statement": "something", "check": "check_that_does_not_exist"}
    )
    results = constitution.all_checks(Registry(data=data, path=registry.path))
    failed = [r for r in results if r.status is Status.FAIL]
    assert any("unimplemented check" in r.summary for r in failed)


def test_temp_harness_does_not_touch_the_real_tree(temp_harness: Path, repo_root: Path) -> None:
    """Guard the guard: fixtures must never write to the checkout."""
    marker = temp_harness / "agents" / "ephemeral.md"
    marker.write_text("Owned subroutine of OmniAGI.\n", encoding="utf-8")
    assert not (repo_root / "agents" / "ephemeral.md").exists()


@pytest.mark.parametrize(
    "pattern",
    [pattern for pattern, _ in constitution.SELF_MASTER_PATTERNS],
)
def test_self_master_patterns_are_valid_regexes(pattern: str) -> None:
    import re

    re.compile(pattern)
