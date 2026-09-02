"""Weighted, explainable routing with a temporally-aware escalation ladder.

The previous router was first-match substring scanning: ``"verify the memory
tool"`` matched ``tool`` and routed to the coder.  ``MEMORY.md`` records that
step-level static routing is strictly worse than temporally-aware routing for
agentic work, so this module implements what the research already argued for:

* weighted keyword scoring with explicit, unique rule priorities for tie-breaks
* a confidence value derived from the margin between candidates
* top-N candidates rather than a single opaque answer
* an escalation ladder that starts cheap and escalates on failure or low
  confidence, carrying attempt count and cumulative cost
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .registry import Registry, load_registry

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#_-]*")


@dataclass(frozen=True)
class Candidate:
    """One scored routing candidate."""

    specialist: str
    seat: str
    engine: str
    score: float
    priority: int
    matched: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialist": self.specialist,
            "seat": self.seat,
            "engine": self.engine,
            "score": round(self.score, 4),
            "priority": self.priority,
            "matched": {k: v for k, v in sorted(self.matched.items())},
        }


@dataclass
class RoutingContext:
    """State carried across attempts for the same task.

    Routing is not a pure function of the prompt: the same task routed for the
    third time after two failures should not go back to the cheapest seat.
    """

    task: str
    attempt: int = 1
    cumulative_cost: float = 0.0
    failures: list[str] = field(default_factory=list)

    def record_failure(self, reason: str, cost: float) -> None:
        self.failures.append(reason)
        self.cumulative_cost += cost
        self.attempt += 1


@dataclass
class Decision:
    """A routing decision plus the full reasoning behind it."""

    task: str
    specialist: str
    seat: str
    engine: str
    confidence: float
    rationale: str
    candidates: list[Candidate]
    attempt: int = 1
    cumulative_cost: float = 0.0
    escalated: bool = False
    exhausted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "specialist": self.specialist,
            "seat": self.seat,
            "engine": self.engine,
            "confidence": round(self.confidence, 4),
            "rationale": self.rationale,
            "attempt": self.attempt,
            "cumulative_cost": round(self.cumulative_cost, 4),
            "escalated": self.escalated,
            "exhausted": self.exhausted,
            "candidates": [c.to_dict() for c in self.candidates],
        }


def tokenize(task: str) -> list[str]:
    return TOKEN_RE.findall(task.lower())


def _token_variants(token: str) -> set[str]:
    variants = {token}
    for suffix in ("s", "es", "ed", "ing"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            variants.add(token[: -len(suffix)])
    return variants


def score_task(task: str, registry: Registry | None = None) -> list[Candidate]:
    """Score every routing rule against ``task``.

    Multi-word keywords are matched as phrases; single words are matched on
    token boundaries (with light suffix normalisation) so ``"tools"`` matches
    ``tool`` but ``"toolkit"`` does not.
    """
    reg = registry or load_registry()
    lowered = task.lower()
    tokens = tokenize(task)
    normalised: set[str] = set()
    for token in tokens:
        normalised |= _token_variants(token)

    candidates: list[Candidate] = []
    for rule in reg.routing["rules"]:
        matched: dict[str, float] = {}
        for keyword, weight in rule["keywords"].items():
            key = keyword.lower()
            if " " in key or "-" in key:
                if key in lowered:
                    matched[keyword] = float(weight)
            elif key in normalised:
                matched[keyword] = float(weight)
        seat = reg.seat(rule["seat"])
        candidates.append(
            Candidate(
                specialist=rule["specialist"],
                seat=rule["seat"],
                engine=seat["engine"] if seat else rule["seat"],
                score=float(sum(matched.values())),
                priority=int(rule["priority"]),
                matched=matched,
            )
        )

    candidates.sort(key=lambda c: (-c.score, c.priority, c.specialist))
    return candidates


#: Score at which the evidence for a route is considered saturated.
SATURATION_SCORE = 5.0


def confidence_of(candidates: list[Candidate]) -> float:
    """Confidence combines evidence strength, share and margin.

    Three separate things can make a route untrustworthy, and all three are
    accounted for:

    * **strength** - one weak keyword is thin evidence even when nothing else
      matched at all;
    * **share** - the winner's portion of the total evidence;
    * **margin** - how far clear of the runner-up it is, so two equally strong
      matches score low even though the total is high.
    """
    scored = [c for c in candidates if c.score > 0]
    if not scored:
        return 0.0
    total = sum(c.score for c in scored)
    top = scored[0].score
    share = top / total if total else 0.0
    runner_up = scored[1].score if len(scored) > 1 else 0.0
    margin = (top - runner_up) / top if top else 0.0
    strength = min(1.0, top / SATURATION_SCORE)
    return round(strength * (0.5 * share + 0.5 * margin), 4)


def route(
    task: str,
    registry: Registry | None = None,
    context: RoutingContext | None = None,
    top_n: int = 3,
) -> Decision:
    """Route ``task`` to a specialist and an engine seat."""
    reg = registry or load_registry()
    if not task.strip():
        raise ValueError("cannot route an empty task")

    ctx = context or RoutingContext(task=task)
    candidates = score_task(task, reg)
    confidence = confidence_of(candidates)
    scored = [c for c in candidates if c.score > 0]

    if scored:
        winner = scored[0]
        specialist, seat_id = winner.specialist, winner.seat
        signals = ", ".join(f"{k}={v:g}" for k, v in sorted(winner.matched.items()))
        rationale = (
            f"'{task}' scored {winner.score:g} for {specialist} "
            f"(priority {winner.priority}; signals: {signals})"
        )
    else:
        default = reg.routing["default"]
        specialist, seat_id = default["specialist"], default["seat"]
        rationale = f"'{task}' matched no routing signal; {default['rationale']}"

    threshold = float(reg.escalation["confidence_threshold"])
    escalated = False
    ladder = list(reg.escalation["ladder"])
    max_attempts = int(reg.escalation["max_attempts"])
    exhausted = ctx.attempt > max_attempts

    if exhausted:
        # Never silently downgrade to a simulated answer: the caller must treat
        # an exhausted ladder as a blocker.
        rationale += (
            f"; escalation ladder exhausted after {max_attempts} attempts - report a blocker"
        )
    elif ctx.attempt > 1:
        # Temporal escalation: previous attempts failed, so climb the ladder.
        index = min(ctx.attempt - 1, len(ladder) - 1)
        seat_id = ladder[index]
        escalated = True
        rationale += (
            f"; escalated to ladder position {index + 1} after {len(ctx.failures)} failure(s)"
        )
    elif confidence < threshold and ladder:
        # Low confidence on the first attempt: start cheap, escalate on failure.
        seat_id = ladder[0]
        escalated = True
        rationale += (
            f"; confidence {confidence:g} < {threshold:g} so starting at the cheapest ladder seat"
        )

    seat = reg.seat(seat_id)
    return Decision(
        task=task,
        specialist=specialist,
        seat=seat_id,
        engine=seat["engine"] if seat else seat_id,
        confidence=confidence,
        rationale=rationale,
        candidates=candidates[:top_n],
        attempt=ctx.attempt,
        cumulative_cost=ctx.cumulative_cost,
        escalated=escalated,
        exhausted=exhausted,
    )


def escalate(decision: Decision, reason: str, registry: Registry | None = None) -> Decision:
    """Record a failure for ``decision`` and re-route at the next ladder rung."""
    reg = registry or load_registry()
    seat = reg.seat(decision.seat)
    cost = float(seat["relative_cost"]) if seat else 0.0
    ctx = RoutingContext(
        task=decision.task,
        attempt=decision.attempt,
        cumulative_cost=decision.cumulative_cost,
    )
    ctx.record_failure(reason, cost)
    return route(decision.task, registry=reg, context=ctx)


def explain(decision: Decision) -> str:
    """Human-readable routing explanation."""
    lines = [
        f"task        : {decision.task}",
        f"specialist  : {decision.specialist}",
        f"seat        : {decision.seat} ({decision.engine})",
        f"confidence  : {decision.confidence:.4f}",
        f"attempt     : {decision.attempt}",
        f"cost so far : {decision.cumulative_cost:g}",
        f"escalated   : {decision.escalated}",
        f"exhausted   : {decision.exhausted}",
        f"rationale   : {decision.rationale}",
        "candidates  :",
    ]
    for index, candidate in enumerate(decision.candidates, start=1):
        signals = ", ".join(f"{k}={v:g}" for k, v in sorted(candidate.matched.items())) or "-"
        lines.append(
            f"  {index}. {candidate.specialist:<14} score={candidate.score:<6g} "
            f"priority={candidate.priority:<4} signals: {signals}"
        )
    return "\n".join(lines)
