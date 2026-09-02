"""Capability-policy and approval tests."""

from __future__ import annotations

import copy

from omniagi import policy
from omniagi.results import Status


def test_committed_policy_passes(registry) -> None:
    result = policy.check_capability_approvals(registry)
    assert result.status is Status.PASS


def test_high_risk_capability_requires_master(registry) -> None:
    decision = policy.authorize("fs_write", registry, actor="master")
    assert decision.allowed
    assert decision.approval == "master"


def test_high_risk_capability_denied_for_non_master(registry) -> None:
    decision = policy.authorize("registry_write", registry, actor="specialist")
    assert not decision.allowed
    assert "only the master" in decision.reason


def test_low_risk_capability_is_auto(registry) -> None:
    decision = policy.authorize("fs_read", registry, actor="specialist")
    assert decision.allowed
    assert decision.approval == "auto"


def test_tool_allowed_requires_all_capabilities(registry) -> None:
    write_tool = next(t for t in registry.tools if t["id"] == "file_write")
    assert policy.tool_allowed(write_tool, registry, actor="master")
    assert not policy.tool_allowed(write_tool, registry, actor="specialist")


def test_undeclared_capability_fails_check(registry) -> None:
    reg = copy.deepcopy(registry)
    reg.tools[0].setdefault("capabilities", []).append("mystery")
    result = policy.check_capability_approvals(reg)
    assert result.status is Status.FAIL
    assert any("undeclared capability" in detail for detail in result.details)


def test_high_risk_auto_approval_is_rejected(registry) -> None:
    reg = copy.deepcopy(registry)
    for rule in reg.policies["capability_rules"]:
        if rule["capability"] == "fs_write":
            rule["approval"] = "auto"
    result = policy.check_capability_approvals(reg)
    assert result.status is Status.FAIL
    assert any("must not be auto-approved" in detail for detail in result.details)


def test_human_approval_gate(registry) -> None:
    reg = copy.deepcopy(registry)
    for rule in reg.policies["capability_rules"]:
        if rule["capability"] == "network":
            rule["approval"] = "human"
    denied = policy.authorize("network", reg, actor="master")
    assert not denied.allowed
    approved = policy.authorize("network", reg, actor="master", human_approved=True)
    assert approved.allowed
