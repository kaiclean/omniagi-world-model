"""Deterministic, offline benchmark/evaluation framework.

A harness that cannot be measured cannot be improved. ``bench`` runs suites of
labelled cases against real harness behaviour and reports accuracy. Every
evaluator here is **deterministic and offline** - it exercises code paths that do
not require a network or credentials (routing today), so the same suite yields
the same score on every machine and in CI.

A suite is a JSON document::

    {
      "name": "routing",
      "kind": "routing",
      "description": "...",
      "min_accuracy": 1.0,
      "cases": [
        {"id": "impl", "task": "implement the parser", "expect": {"specialist": "coder"}}
      ]
    }

``expect`` keys are evaluator-specific; a routing case may assert ``specialist``,
``seat``, ``min_confidence`` and/or ``max_confidence``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import routing
from .paths import resolve
from .registry import Registry, load_registry

BENCHMARKS_DIRNAME = "benchmarks"


class BenchError(RuntimeError):
    """Raised when a benchmark suite is missing or malformed."""


@dataclass(frozen=True)
class Case:
    id: str
    task: str
    expect: dict[str, Any]
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CaseResult:
    id: str
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ok": self.ok,
            "expected": self.expected,
            "actual": self.actual,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class SuiteResult:
    name: str
    kind: str
    min_accuracy: float
    results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total else 1.0

    @property
    def ok(self) -> bool:
        return self.accuracy >= self.min_accuracy

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "total": self.total,
            "passed": self.passed,
            "accuracy": round(self.accuracy, 4),
            "min_accuracy": self.min_accuracy,
            "ok": self.ok,
            "cases": [r.to_dict() for r in self.results],
        }


# -- evaluators ----------------------------------------------------------------

Evaluator = Callable[[Case, Registry], "tuple[dict[str, Any], list[str]]"]


def _evaluate_routing(case: Case, reg: Registry) -> tuple[dict[str, Any], list[str]]:
    decision = routing.route(case.task, reg)
    actual = {
        "specialist": decision.specialist,
        "seat": decision.seat,
        "confidence": round(decision.confidence, 4),
    }
    reasons: list[str] = []
    expect = case.expect
    if "specialist" in expect and decision.specialist != expect["specialist"]:
        reasons.append(f"specialist: expected {expect['specialist']!r}, got {decision.specialist!r}")
    if "seat" in expect and decision.seat != expect["seat"]:
        reasons.append(f"seat: expected {expect['seat']!r}, got {decision.seat!r}")
    if "min_confidence" in expect and decision.confidence < float(expect["min_confidence"]):
        reasons.append(f"confidence {decision.confidence:g} < min {float(expect['min_confidence']):g}")
    if "max_confidence" in expect and decision.confidence > float(expect["max_confidence"]):
        reasons.append(f"confidence {decision.confidence:g} > max {float(expect['max_confidence']):g}")
    return actual, reasons


EVALUATORS: dict[str, Evaluator] = {"routing": _evaluate_routing}


# -- loading and running -------------------------------------------------------


def load_suite(path: Path) -> tuple[str, str, float, list[Case]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchError(f"cannot read benchmark suite {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BenchError(f"benchmark suite {path} must be a JSON object")
    kind = data.get("kind")
    if kind not in EVALUATORS:
        raise BenchError(f"benchmark suite {path} has unknown kind {kind!r}")
    name = str(data.get("name") or path.stem)
    min_accuracy = float(data.get("min_accuracy", 1.0))
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise BenchError(f"benchmark suite {path} has no cases")
    cases: list[Case] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise BenchError(f"{path}: case {index} is not an object")
        case_id = str(raw.get("id") or f"case-{index}")
        if case_id in seen:
            raise BenchError(f"{path}: duplicate case id {case_id!r}")
        seen.add(case_id)
        task = raw.get("task")
        if not isinstance(task, str) or not task.strip():
            raise BenchError(f"{path}: case {case_id!r} has no task")
        expect = raw.get("expect") or {}
        if not isinstance(expect, dict):
            raise BenchError(f"{path}: case {case_id!r} has a non-object expect")
        cases.append(Case(case_id, task, expect, list(raw.get("tags", []))))
    return name, kind, min_accuracy, cases


def run_suite(
    name: str,
    kind: str,
    min_accuracy: float,
    cases: list[Case],
    registry: Registry | None = None,
) -> SuiteResult:
    reg = registry or load_registry()
    evaluator = EVALUATORS[kind]
    results: list[CaseResult] = []
    for case in cases:
        actual, reasons = evaluator(case, reg)
        results.append(CaseResult(case.id, not reasons, case.expect, actual, reasons))
    return SuiteResult(name, kind, min_accuracy, results)


def run_file(path: Path, registry: Registry | None = None) -> SuiteResult:
    name, kind, min_accuracy, cases = load_suite(path)
    return run_suite(name, kind, min_accuracy, cases, registry)


def discover(directory: Path | None = None) -> list[Path]:
    root = directory or resolve(BENCHMARKS_DIRNAME)
    if not root.is_dir():
        return []
    return sorted(root.glob("*.json"))


def run_all(directory: Path | None = None, registry: Registry | None = None) -> list[SuiteResult]:
    reg = registry or load_registry()
    return [run_file(path, reg) for path in discover(directory)]


def format_report(suites: list[SuiteResult], verbose: bool = False) -> str:
    lines = ["OmniAGI benchmark evaluation", "=" * 60]
    if not suites:
        lines.append("no benchmark suites found under benchmarks/")
        lines.append("=" * 60)
        return "\n".join(lines)
    for suite in suites:
        status = "PASS" if suite.ok else "FAIL"
        lines.append(
            f"[{status}] {suite.name:<20} {suite.passed}/{suite.total} "
            f"({suite.accuracy:.0%}, min {suite.min_accuracy:.0%})"
        )
        for case in suite.results:
            if verbose or not case.ok:
                mark = "ok" if case.ok else "XX"
                lines.append(f"    [{mark}] {case.id}")
                for reason in case.reasons:
                    lines.append(f"         - {reason}")
    lines.append("=" * 60)
    total = sum(s.total for s in suites)
    passed = sum(s.passed for s in suites)
    lines.append(f"suites={len(suites)} cases={total} passed={passed}")
    lines.append(f"RESULT: {'PASS' if all(s.ok for s in suites) else 'FAIL'}")
    return "\n".join(lines)
