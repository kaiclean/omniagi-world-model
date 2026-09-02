"""Capability policy and approvals.

Tools declare the *capabilities* they exercise (filesystem write, process
execution, network, registry write, ...). The registry's ``policies`` section
maps each capability to an approval level:

* ``auto``  - the capability may be used without asking.
* ``master`` - only the single master may authorise it.
* ``human`` - a human operator must approve out of band.

This module turns those declarations into an executed decision: given a tool
and the current actor, :func:`authorize` returns an allow/deny decision with the
governing rule, and :func:`check_capability_approvals` proves at verification
time that every capability a tool uses is governed by a policy rule and that the
most dangerous capabilities are never left on ``auto``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .registry import Registry, load_registry
from .results import CheckResult

APPROVAL_LEVELS = ("auto", "master", "human")
#: High-risk capabilities must never be self-approved (``auto``).
GUARDED_RISKS = frozenset({"high"})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    capability: str
    approval: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "capability": self.capability,
            "approval": self.approval,
            "reason": self.reason,
        }


def approval_for(capability: str, registry: Registry) -> str:
    """The approval level governing ``capability`` (falls back to the default)."""
    policies = registry.policies
    for rule in policies.get("capability_rules", []):
        if rule["capability"] == capability:
            return str(rule["approval"])
    return str(policies.get("default_approval", "master"))


def authorize(
    capability: str, registry: Registry, actor: str = "master", human_approved: bool = False
) -> Decision:
    """Decide whether ``actor`` may exercise ``capability`` right now."""
    approval = approval_for(capability, registry)
    if approval == "auto":
        return Decision(True, capability, approval, "capability is auto-approved")
    if approval == "master":
        allowed = actor == "master"
        reason = (
            "master authorised the capability"
            if allowed
            else f"only the master may authorise '{capability}'"
        )
        return Decision(allowed, capability, approval, reason)
    # human
    reason = (
        "human operator approved the capability"
        if human_approved
        else f"'{capability}' needs out-of-band human approval"
    )
    return Decision(human_approved, capability, approval, reason)


def authorize_tool(
    tool: dict[str, Any],
    registry: Registry,
    actor: str = "master",
    human_approved: bool = False,
) -> list[Decision]:
    """Authorise every capability a tool declares."""
    return [
        authorize(capability, registry, actor=actor, human_approved=human_approved)
        for capability in tool.get("capabilities", [])
    ]


def tool_allowed(
    tool: dict[str, Any],
    registry: Registry,
    actor: str = "master",
    human_approved: bool = False,
) -> bool:
    """Whether every capability a tool needs is authorised for ``actor``."""
    return all(
        decision.allowed
        for decision in authorize_tool(tool, registry, actor=actor, human_approved=human_approved)
    )


def check_capability_approvals(registry: Registry | None = None) -> CheckResult:
    """Verify the capability-approval policy is complete and safe."""
    reg = load_registry() if registry is None else registry
    name = "policy.capability_approvals"
    if not reg.policies:
        return CheckResult.warned(name, "no capability policy is declared")

    errors: list[str] = []
    capability_ids = {cap["id"] for cap in reg.capabilities}
    risk_by_id = {cap["id"]: cap["risk"] for cap in reg.capabilities}

    for rule in reg.policies.get("capability_rules", []):
        if rule["approval"] not in APPROVAL_LEVELS:
            errors.append(
                f"capability '{rule['capability']}' has invalid approval '{rule['approval']}'"
            )
        if risk_by_id.get(rule["capability"]) in GUARDED_RISKS and rule["approval"] == "auto":
            errors.append(
                f"high-risk capability '{rule['capability']}' must not be auto-approved"
            )

    # Every capability a tool actually uses must be governed by a rule.
    for tool in reg.tools:
        for capability in tool.get("capabilities", []):
            if capability not in capability_ids:
                errors.append(
                    f"tool '{tool['id']}' uses undeclared capability '{capability}'"
                )
            elif not _has_rule(capability, reg):
                errors.append(
                    f"capability '{capability}' used by '{tool['id']}' has no policy rule"
                )

    if errors:
        return CheckResult.failed(name, "capability policy is incomplete or unsafe", errors)
    guarded = sum(
        1
        for cap in reg.capabilities
        if cap["risk"] in GUARDED_RISKS and approval_for(cap["id"], reg) != "auto"
    )
    return CheckResult.passed(
        name,
        f"all tool capabilities are governed; {guarded} high-risk capabilities require approval",
    )


def _has_rule(capability: str, registry: Registry) -> bool:
    return any(
        rule["capability"] == capability
        for rule in registry.policies.get("capability_rules", [])
    )
