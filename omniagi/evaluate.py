"""Task-fixture evaluation: pass/fail on behaviour, not on prose.

"The markdown still has a Verify heading" is not a test of anything. This
module replays a fixture of tasks through the real closed loop
(:mod:`omniagi.loop`) with recorded model replies, executes the tool calls for
real inside a throwaway harness copy, and scores each task against its declared
expectation.

Fixture format (``tests/fixtures/loop_tasks.json``)::

    {
      "version": 1,
      "tasks": [
        {
          "id": "t01",
          "prompt": "...",
          "reply": "...model text containing tool calls...",
          "expect": {
            "verified": true,
            "specialist": "coder",
            "tools": ["file_write"],
            "error_contains": "..."
          }
        }
      ]
    }

Only ``id``, ``prompt``, ``reply`` and ``expect.verified`` are required; the
rest are optional assertions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .extend import temporary_harness
from .loop import LoopError, LoopResult, ScriptedTransport, run_loop
from .paths import resolve
from .registry import load_registry
from .results import CheckResult

DEFAULT_FIXTURE = "tests/fixtures/loop_tasks.json"


class FixtureError(RuntimeError):
    """Raised when the fixture file is missing or malformed."""


@dataclass
class TaskOutcome:
    task_id: str
    prompt: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.task_id,
            "prompt": self.prompt,
            "passed": self.passed,
            "reasons": list(self.reasons),
            "detail": dict(self.detail),
        }


@dataclass
class EvalReport:
    outcomes: list[TaskOutcome]

    @property
    def failed(self) -> list[TaskOutcome]:
        return [outcome for outcome in self.outcomes if not outcome.passed]

    @property
    def ok(self) -> bool:
        return not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": "PASS" if self.ok else "FAIL",
            "total": len(self.outcomes),
            "passed": len(self.outcomes) - len(self.failed),
            "failed": len(self.failed),
            "tasks": [outcome.to_dict() for outcome in self.outcomes],
        }


def load_fixture(path: Path | str | None = None) -> list[dict[str, Any]]:
    target = Path(path) if path else resolve(DEFAULT_FIXTURE)
    if not target.is_file():
        raise FixtureError(f"task fixture not found: {target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"task fixture is not valid JSON: {exc}") from exc
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise FixtureError("task fixture contains no tasks")
    for task in tasks:
        missing = [key for key in ("id", "prompt", "reply", "expect") if key not in task]
        if missing:
            raise FixtureError(f"task {task.get('id', '?')} is missing {', '.join(missing)}")
    return tasks


def score(task: dict[str, Any], result: LoopResult) -> list[str]:
    """Return the reasons ``result`` fails ``task``'s expectations (empty = pass)."""
    expect = task["expect"]
    reasons: list[str] = []

    if result.verified is not bool(expect["verified"]):
        reasons.append(
            f"expected verified={expect['verified']}, got {result.verified} ({result.verdict})"
        )
    if "specialist" in expect and result.decision.specialist != expect["specialist"]:
        reasons.append(
            f"expected specialist '{expect['specialist']}', routed to "
            f"'{result.decision.specialist}'"
        )
    if "tools" in expect:
        actual = [call.tool for call in result.calls]
        if actual != list(expect["tools"]):
            reasons.append(f"expected tool calls {expect['tools']}, executed {actual}")
    if "error_contains" in expect:
        errors = " | ".join(call.error or "" for call in result.calls)
        if expect["error_contains"] not in errors:
            reasons.append(
                f"expected an error containing {expect['error_contains']!r}, got {errors!r}"
            )
    if "file_contains" in expect:
        for rel, needle in expect["file_contains"].items():
            target = resolve(rel)
            body = target.read_text(encoding="utf-8") if target.is_file() else ""
            if needle not in body:
                reasons.append(f"expected {rel} to contain {needle!r}")
    return reasons


def run_task(task: dict[str, Any]) -> TaskOutcome:
    """Run one fixture task in a throwaway harness copy."""
    with temporary_harness():
        transport = ScriptedTransport(replies=[task["reply"]])
        try:
            result = run_loop(
                task["prompt"],
                transport=transport,
                registry=load_registry(),
                log=bool(task.get("log", False)),
            )
        except LoopError as exc:
            return TaskOutcome(
                task_id=task["id"],
                prompt=task["prompt"],
                passed=False,
                reasons=[f"loop raised: {exc}"],
            )
        reasons = score(task, result)
        return TaskOutcome(
            task_id=task["id"],
            prompt=task["prompt"],
            passed=not reasons,
            reasons=reasons,
            detail=result.to_dict(),
        )


def evaluate(path: Path | str | None = None) -> EvalReport:
    """Run every fixture task and score it."""
    tasks = load_fixture(path)
    return EvalReport([run_task(task) for task in tasks])


def check_fixture(path: Path | str | None = None) -> CheckResult:
    """Fixture evaluation as a named check, for ``omniagi check`` style reporting."""
    name = "loop.task_fixture"
    try:
        report = evaluate(path)
    except FixtureError as exc:
        return CheckResult.failed(name, str(exc))
    errors = [
        f"{outcome.task_id}: {'; '.join(outcome.reasons)}" for outcome in report.failed
    ]
    return CheckResult.from_errors(
        name,
        errors,
        f"{len(report.outcomes)} fixture tasks behaved as specified",
        "fixture tasks did not behave as specified",
    )


def format_report(report: EvalReport) -> str:
    lines = ["OmniAGI task fixture", "=" * 60]
    for outcome in report.outcomes:
        lines.append(f"[{'PASS' if outcome.passed else 'FAIL'}] {outcome.task_id:<6} {outcome.prompt}")
        for reason in outcome.reasons:
            lines.append(f"         - {reason}")
    counts = report.to_dict()
    lines.append("=" * 60)
    lines.append(f"passed={counts['passed']} failed={counts['failed']} of {counts['total']}")
    lines.append(f"RESULT: {counts['result']}")
    return "\n".join(lines)
