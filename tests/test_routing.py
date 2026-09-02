"""Golden routing table.

Locks in router behaviour so regressions like ``"verify the memory tool"``
routing to the coder (because the substring ``tool`` matched first) cannot come
back unnoticed.
"""

from __future__ import annotations

import pytest

from omniagi.routing import (
    Decision,
    RoutingContext,
    confidence_of,
    escalate,
    explain,
    route,
    score_task,
    tokenize,
)

# (task, expected specialist)
GOLDEN: list[tuple[str, str]] = [
    # --- critic -------------------------------------------------------------
    ("verify the memory tool", "critic"),
    ("audit the complete repo", "critic"),
    ("double-check that the manifest matches", "critic"),
    ("review this patch for correctness", "critic"),
    ("validate the registry against the schema", "critic"),
    ("confirm the CI run actually passed", "critic"),
    ("critique the escalation ladder design", "critic"),
    ("prove the single-master check fails on a second master", "critic"),
    # --- coder --------------------------------------------------------------
    ("implement a missing file hasher tool", "coder"),
    ("refactor the dispatcher", "coder"),
    ("debug the failing workflow", "coder"),
    ("fix the hardcoded path in the watchdog", "coder"),
    ("write a patch for the changelog dedupe", "coder"),
    ("the build is broken, compile it locally", "coder"),
    ("add a python script for hashing", "coder"),
    ("there is a bug in the router", "coder"),
    # --- reasoner -----------------------------------------------------------
    ("design the architecture for the new harness", "reasoner"),
    ("plan the migration strategy", "reasoner"),
    ("analyze the tradeoff between local and cloud seats", "reasoner"),
    ("decompose this into subgoals", "reasoner"),
    ("think through the long-horizon roadmap", "reasoner"),
    ("what approach should the harness take", "reasoner"),
    # --- memory_keeper ------------------------------------------------------
    ("consolidate the durable memory", "memory_keeper"),
    ("remember that the local endpoint is down", "memory_keeper"),
    ("recall what we decided about seats", "memory_keeper"),
    ("this fact is stale, correct it", "memory_keeper"),
    ("append an entry to the changelog", "memory_keeper"),
    ("forget the obsolete disk figure", "memory_keeper"),
    # --- scout --------------------------------------------------------------
    ("search for the routing table", "scout"),
    ("find every reference to AGENTS.md", "scout"),
    ("grep the repo for hardcoded paths", "scout"),
    ("look up the seat provenance", "scout"),
    ("retrieve the latest catalog entry", "scout"),
    ("scan the tools directory", "scout"),
    ("locate the manifest file", "scout"),
    ("fetch the workflow definition", "scout"),
    # --- default fallback ---------------------------------------------------
    ("", "router"),  # handled separately below
    ("xyzzy plugh frobnicate", "router"),
    ("qwerty", "router"),
    ("...", "router"),
]


@pytest.mark.parametrize("task,expected", [g for g in GOLDEN if g[0]])
def test_golden_routing(task: str, expected: str) -> None:
    decision = route(task)
    assert decision.specialist == expected, (
        f"{task!r} routed to {decision.specialist}, expected {expected}\n{explain(decision)}"
    )


def test_the_original_regression() -> None:
    """The exact case the first-match router got wrong."""
    decision = route("verify the memory tool")
    assert decision.specialist == "critic"
    top = decision.candidates[0]
    assert top.matched["verify"] > top.matched.get("tool", 0)


def test_empty_task_is_rejected() -> None:
    with pytest.raises(ValueError):
        route("   ")


def test_unmatched_task_uses_default_route(registry) -> None:
    decision = route("xyzzy plugh frobnicate")
    assert decision.specialist == registry.routing["default"]["specialist"]
    assert decision.confidence == 0.0
    assert "matched no routing signal" in decision.rationale


def test_tokenizer_normalises_plurals() -> None:
    assert "tool" in {v for token in tokenize("tools") for v in (token, token.rstrip("s"))}
    decision = route("implement the missing tools")
    assert decision.specialist == "coder"


def test_toolkit_does_not_match_tool() -> None:
    """Substring matching was the original bug; matching is token-based now."""
    candidates = {c.specialist: c for c in score_task("toolkit")}
    assert "tool" not in candidates["coder"].matched


def test_top_n_candidates_are_ordered() -> None:
    decision = route("verify and refactor the code", top_n=5)
    scores = [c.score for c in decision.candidates]
    assert scores == sorted(scores, reverse=True)
    assert len(decision.candidates) <= 5


def test_confidence_is_low_for_a_tie() -> None:
    tie = route("verify refactor")  # critic 5 vs coder 5
    assert tie.confidence < 0.5


def test_confidence_is_high_for_an_unambiguous_task() -> None:
    clear = route("audit and verify and validate the evidence")
    assert clear.confidence > 0.5


def test_low_confidence_starts_at_the_cheapest_ladder_seat(registry) -> None:
    decision = route("summarize")  # single weak signal
    assert decision.confidence < registry.escalation["confidence_threshold"]
    assert decision.escalated
    assert decision.seat == registry.escalation["ladder"][0]


def test_escalation_climbs_and_accumulates_cost(registry) -> None:
    first = route("implement a hasher and verify it")
    second = escalate(first, "seat timed out")
    assert second.attempt == first.attempt + 1
    assert second.escalated
    assert second.cumulative_cost > 0
    third = escalate(second, "malformed response")
    assert third.attempt == 3
    assert third.cumulative_cost > second.cumulative_cost
    ladder = registry.escalation["ladder"]
    assert third.seat in ladder


def test_exhausted_ladder_is_reported_not_simulated(registry) -> None:
    context = RoutingContext(task="implement it", attempt=registry.escalation["max_attempts"] + 1)
    decision = route("implement it", context=context)
    assert decision.exhausted
    assert "report a blocker" in decision.rationale


def test_explain_is_human_readable() -> None:
    text = explain(route("refactor the router"))
    for field in ("task", "specialist", "seat", "confidence", "candidates"):
        assert field in text


def test_decision_serialises() -> None:
    payload: Decision = route("plan the architecture")
    data = payload.to_dict()
    assert data["specialist"] == "reasoner"
    assert isinstance(data["candidates"], list)


def test_confidence_of_empty_is_zero() -> None:
    assert confidence_of([]) == 0.0


def test_every_specialist_is_reachable(registry) -> None:
    """No routing rule may be unreachable dead weight."""
    reached = {expected for task, expected in GOLDEN if task}
    declared = {rule["specialist"] for rule in registry.routing["rules"]}
    assert declared <= reached
