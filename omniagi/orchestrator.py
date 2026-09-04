"""Autonomous run lifecycle: a bounded, checkpointed task DAG.

``omniagi run`` turns the harness from a set of one-shot commands into an
observable agent loop. A *plan* is a directed acyclic graph of tasks; the
orchestrator schedules ready tasks, executes each one with routing, retries,
escalation and a critic, records the evidence it gathered, and checkpoints the
whole run after every task so an interrupted run can be resumed.

Everything is bounded. A :class:`Budget` (seeded from ``registry.budgets``)
caps the number of steps, the wall-clock seconds, the per-task retries and the
cumulative routing cost. When a budget is exhausted the run halts with a
recorded blocker instead of looping forever.

The default executors are deliberately offline-safe and deterministic:

* ``verify`` runs the harness self-check and treats a FAIL as a rejected task;
* ``route`` produces a routing decision (the seat the master *would* use);
* ``noop`` records a manual/human step;
* ``model`` actually calls an engine seat and, with no credentials, reports a
  blocker rather than fabricating output.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import resolve
from .persistence import atomic_write_json
from .registry import Registry, load_registry
from .routing import Decision, escalate, route

STATE_DIRNAME = "runs"
TERMINAL_STATES = frozenset({"done", "failed", "blocked", "skipped"})


class OrchestratorError(RuntimeError):
    """Raised when a plan is malformed or a run cannot proceed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- data model ----------------------------------------------------------------


@dataclass
class Attempt:
    number: int
    seat: str
    status: str  # accepted | rejected | blocked | error
    reason: str
    cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "seat": self.seat,
            "status": self.status,
            "reason": self.reason,
            "cost": round(self.cost, 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attempt:
        return cls(
            number=int(data["number"]),
            seat=data["seat"],
            status=data["status"],
            reason=data["reason"],
            cost=float(data["cost"]),
        )


@dataclass
class Task:
    id: str
    description: str
    kind: str = "noop"
    depends_on: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    state: str = "pending"
    attempts: list[Attempt] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
            "params": dict(self.params),
            "state": self.state,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "observations": list(self.observations),
            "evidence": dict(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        return cls(
            id=data["id"],
            description=data.get("description", ""),
            kind=data.get("kind", "noop"),
            depends_on=list(data.get("depends_on", [])),
            params=dict(data.get("params", {})),
            state=data.get("state", "pending"),
            attempts=[Attempt.from_dict(a) for a in data.get("attempts", [])],
            observations=list(data.get("observations", [])),
            evidence=dict(data.get("evidence", {})),
        )


@dataclass
class Budget:
    max_steps: int = 64
    max_seconds: float = 900.0
    max_retries: int = 3
    max_cost: float = 1000.0

    @classmethod
    def from_registry(cls, registry: Registry) -> Budget:
        data = registry.default_budget()
        return cls(
            max_steps=int(data.get("max_steps", 64)),
            max_seconds=float(data.get("max_seconds", 900.0)),
            max_retries=int(data.get("max_retries", 3)),
            max_cost=float(data.get("max_cost", 1000.0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_seconds": self.max_seconds,
            "max_retries": self.max_retries,
            "max_cost": self.max_cost,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Budget:
        return cls(
            max_steps=int(data["max_steps"]),
            max_seconds=float(data["max_seconds"]),
            max_retries=int(data["max_retries"]),
            max_cost=float(data["max_cost"]),
        )


@dataclass
class RunState:
    run_id: str
    goal: str
    tasks: list[Task]
    budget: Budget
    status: str = "pending"
    spent_steps: int = 0
    spent_seconds: float = 0.0
    spent_cost: float = 0.0
    blockers: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def task(self, task_id: str) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise OrchestratorError(f"unknown task '{task_id}'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "status": self.status,
            "budget": self.budget.to_dict(),
            "spent": {
                "steps": self.spent_steps,
                "seconds": round(self.spent_seconds, 3),
                "cost": round(self.spent_cost, 4),
            },
            "blockers": list(self.blockers),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "tasks": [task.to_dict() for task in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunState:
        spent = data.get("spent", {})
        state = cls(
            run_id=data["run_id"],
            goal=data.get("goal", ""),
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
            budget=Budget.from_dict(data["budget"]),
            status=data.get("status", "pending"),
            spent_steps=int(spent.get("steps", 0)),
            spent_seconds=float(spent.get("seconds", 0.0)),
            spent_cost=float(spent.get("cost", 0.0)),
            blockers=list(data.get("blockers", [])),
            started_at=data.get("started_at", _now()),
            updated_at=data.get("updated_at", _now()),
        )
        return state


# -- executors and critic ------------------------------------------------------


@dataclass
class Outcome:
    ok: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    retryable: bool = True
    blocked: bool = False


Executor = Callable[[Task, Decision, Registry], Outcome]
Critic = Callable[[Task, Outcome, Decision, Registry], "tuple[bool, str]"]


def _verify_executor(task: Task, decision: Decision, registry: Registry) -> Outcome:
    from .selfcheck import run_checks

    report = run_checks(registry)
    failed = [result.name for result in report.results if not result.ok]
    warned = [result.name for result in report.results if result.status.value == "WARN"]
    evidence = {
        "passed": sum(1 for r in report.results if r.status.value == "PASS"),
        "warned": warned,
        "failed": failed,
    }
    if failed:
        return Outcome(
            ok=False,
            reason=f"self-check failed: {', '.join(failed)}",
            evidence=evidence,
            observation=f"{len(failed)} check(s) failing",
            retryable=False,
        )
    return Outcome(
        ok=True,
        reason="self-check passed",
        evidence=evidence,
        observation=f"harness verified ({len(warned)} warning(s))",
        retryable=False,
    )


def _route_executor(task: Task, decision: Decision, registry: Registry) -> Outcome:
    if decision.exhausted:
        return Outcome(
            ok=False,
            reason="escalation ladder exhausted",
            evidence={"decision": decision.to_dict()},
            observation=decision.rationale,
            retryable=False,
        )
    return Outcome(
        ok=True,
        reason=decision.rationale,
        evidence={"decision": decision.to_dict()},
        observation=f"routed to {decision.engine} via {decision.specialist}",
    )


def _noop_executor(task: Task, decision: Decision, registry: Registry) -> Outcome:
    note = str(task.params.get("note", "manual step recorded"))
    return Outcome(ok=True, reason=note, evidence={"note": note}, observation=note, retryable=False)


def _model_executor(task: Task, decision: Decision, registry: Registry) -> Outcome:
    from .adapters import SeatUnavailable, call_seat

    prompt = str(task.params.get("prompt", task.description))
    try:
        response = call_seat(prompt, decision.seat, registry=registry)
    except SeatUnavailable as exc:
        return Outcome(
            ok=False,
            reason=str(exc),
            observation="model seat unavailable - reported as a blocker",
            blocked=True,
        )
    return Outcome(
        ok=True,
        reason="model returned content",
        evidence={"engine": response.engine, "content": response.content},
        observation=f"{response.engine} responded with {len(response.content)} chars",
    )


DEFAULT_EXECUTORS: dict[str, Executor] = {
    "verify": _verify_executor,
    "route": _route_executor,
    "noop": _noop_executor,
    "model": _model_executor,
}


def default_critic(
    task: Task, outcome: Outcome, decision: Decision, registry: Registry
) -> tuple[bool, str]:
    """Accept or reject an executor outcome, recording the critic's reasoning."""
    if not outcome.ok:
        return False, outcome.reason
    if task.kind == "model":
        content = str(outcome.evidence.get("content", ""))
        minimum = int(task.params.get("min_chars", 1))
        if len(content) < minimum:
            return False, f"model output too short ({len(content)} < {minimum} chars)"
    return True, outcome.reason


# -- orchestrator --------------------------------------------------------------


class Orchestrator:
    """Schedule and execute a plan as a bounded, checkpointed task DAG."""

    def __init__(
        self,
        state: RunState,
        registry: Registry | None = None,
        executors: dict[str, Executor] | None = None,
        critic: Critic | None = None,
        clock: Callable[[], float] | None = None,
        state_dir: Path | None = None,
        trace: Any | None = None,
    ) -> None:
        self.state = state
        self.registry = registry or load_registry()
        self.executors = executors or DEFAULT_EXECUTORS
        self.critic = critic or default_critic
        self._clock = clock or time.monotonic
        self.state_dir = state_dir or resolve(STATE_DIRNAME)
        self.trace = trace
        self._session_start = self._clock()

    # -- construction ----------------------------------------------------------

    @classmethod
    def from_plan(
        cls,
        plan: dict[str, Any],
        run_id: str,
        registry: Registry | None = None,
        budget: Budget | None = None,
        **kwargs: Any,
    ) -> Orchestrator:
        reg = registry or load_registry()
        tasks = [Task.from_dict(entry) for entry in plan.get("tasks", [])]
        if not tasks:
            raise OrchestratorError("plan contains no tasks")
        _validate_dag(tasks)
        state = RunState(
            run_id=run_id,
            goal=str(plan.get("goal", "")),
            tasks=tasks,
            budget=budget or Budget.from_registry(reg),
        )
        return cls(state, registry=reg, **kwargs)

    @classmethod
    def resume(
        cls, run_id: str, registry: Registry | None = None, state_dir: Path | None = None,
        **kwargs: Any,
    ) -> Orchestrator:
        directory = state_dir or resolve(STATE_DIRNAME)
        path = directory / run_id / "state.json"
        if not path.is_file():
            raise OrchestratorError(f"no checkpoint to resume at {path}")
        import json

        state = RunState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        _validate_dag(state.tasks)
        return cls(state, registry=registry, state_dir=directory, **kwargs)

    # -- persistence -----------------------------------------------------------

    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / self.state.run_id / "state.json"

    def checkpoint(self) -> Path:
        self.state.updated_at = _now()
        return atomic_write_json(self.checkpoint_path, self.state.to_dict())

    # -- scheduling ------------------------------------------------------------

    def run(self) -> RunState:
        self._emit("run_start", goal=self.state.goal, tasks=len(self.state.tasks))
        if self.state.status in ("completed", "failed"):
            return self.state
        self.state.status = "running"
        while True:
            reason = self._exceeded_budget()
            if reason is not None:
                self.state.status = "exhausted"
                self.state.blockers.append(reason)
                self._emit("run_halted", reason=reason)
                break
            self._propagate_blocks()
            task = self._next_ready()
            if task is None:
                break
            self._execute_task(task)
            self.checkpoint()
            if self.state.status == "exhausted":
                break
        self._finalize()
        self.checkpoint()
        self._emit("run_end", status=self.state.status)
        return self.state

    def _next_ready(self) -> Task | None:
        for task in self.state.tasks:
            if task.state != "pending":
                continue
            if all(self.state.task(dep).state == "done" for dep in task.depends_on):
                return task
        return None

    def _propagate_blocks(self) -> None:
        changed = True
        while changed:
            changed = False
            for task in self.state.tasks:
                if task.state != "pending":
                    continue
                for dep in task.depends_on:
                    if self.state.task(dep).state in ("failed", "blocked", "skipped"):
                        task.state = "blocked"
                        note = f"blocked by upstream task '{dep}'"
                        task.observations.append(note)
                        self.state.blockers.append(f"{task.id}: {note}")
                        changed = True
                        break

    def _execute_task(self, task: Task) -> None:
        executor = self.executors.get(task.kind)
        if executor is None:
            task.state = "failed"
            reason = f"no executor for task kind '{task.kind}'"
            task.observations.append(reason)
            self.state.blockers.append(f"{task.id}: {reason}")
            self._emit("task_end", task=task.id, state=task.state, reason=reason)
            return

        self._emit("task_start", task=task.id, task_kind=task.kind)
        decision = route(task.description or task.id, registry=self.registry)
        attempt_number = 1
        while True:
            budget_reason = self._exceeded_budget()
            if budget_reason is not None:
                self.state.status = "exhausted"
                self.state.blockers.append(f"{task.id}: {budget_reason}")
                self._emit("task_end", task=task.id, state=task.state, reason=budget_reason)
                return

            outcome = executor(task, decision, self.registry)
            cost = self._seat_cost(decision.seat)
            self.state.spent_steps += 1
            self.state.spent_cost += cost

            if outcome.blocked:
                task.attempts.append(
                    Attempt(attempt_number, decision.seat, "blocked", outcome.reason, cost)
                )
                task.observations.append(outcome.observation or outcome.reason)
                task.state = "blocked"
                self.state.blockers.append(f"{task.id}: {outcome.reason}")
                self._emit("task_end", task=task.id, state=task.state, reason=outcome.reason)
                return

            accepted, verdict = self.critic(task, outcome, decision, self.registry)
            task.attempts.append(
                Attempt(
                    attempt_number,
                    decision.seat,
                    "accepted" if accepted else "rejected",
                    verdict,
                    cost,
                )
            )
            if outcome.observation:
                task.observations.append(outcome.observation)

            if accepted:
                task.state = "done"
                task.evidence = outcome.evidence
                self._emit("task_end", task=task.id, state=task.state, attempts=attempt_number)
                return

            if not outcome.retryable or attempt_number > self.state.budget.max_retries:
                task.state = "failed"
                self.state.blockers.append(f"{task.id}: {verdict}")
                self._emit("task_end", task=task.id, state=task.state, reason=verdict)
                return

            decision = escalate(decision, verdict, registry=self.registry)
            attempt_number += 1

    # -- helpers ---------------------------------------------------------------

    def _seat_cost(self, seat_id: str) -> float:
        seat = self.registry.seat(seat_id)
        return float(seat["relative_cost"]) if seat else 0.0

    def _elapsed(self) -> float:
        return self.state.spent_seconds + (self._clock() - self._session_start)

    def _exceeded_budget(self) -> str | None:
        budget = self.state.budget
        if self.state.spent_steps >= budget.max_steps:
            return f"step budget exhausted ({budget.max_steps})"
        if self.state.spent_cost > budget.max_cost:
            return f"cost budget exhausted ({budget.max_cost:g})"
        if self._elapsed() > budget.max_seconds:
            return f"time budget exhausted ({budget.max_seconds:g}s)"
        return None

    def _finalize(self) -> None:
        self.state.spent_seconds = self._elapsed()
        if self.state.status == "exhausted":
            return
        states = {task.state for task in self.state.tasks}
        if "failed" in states:
            self.state.status = "failed"
        elif "blocked" in states:
            self.state.status = "blocked"
        elif states <= {"done", "skipped"}:
            self.state.status = "completed"
        else:
            self.state.status = "failed"

    def _emit(self, kind: str, **fields: Any) -> None:
        if self.trace is not None:
            self.trace.event(kind, run=self.state.run_id, **fields)


def _validate_dag(tasks: list[Task]) -> None:
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise OrchestratorError("plan has duplicate task ids")
    known = set(ids)
    for task in tasks:
        for dep in task.depends_on:
            if dep not in known:
                raise OrchestratorError(f"task '{task.id}' depends on unknown task '{dep}'")
            if dep == task.id:
                raise OrchestratorError(f"task '{task.id}' depends on itself")
    _detect_cycle(tasks)


def _detect_cycle(tasks: list[Task]) -> None:
    graph = {task.id: list(task.depends_on) for task in tasks}
    color: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        color[node] = 1
        for dep in graph[node]:
            if color.get(dep, 0) == 1:
                cycle = " -> ".join([*stack, node, dep])
                raise OrchestratorError(f"plan has a dependency cycle: {cycle}")
            if color.get(dep, 0) == 0:
                visit(dep, [*stack, node])
        color[node] = 2

    for task in tasks:
        if color.get(task.id, 0) == 0:
            visit(task.id, [])


def load_plan(path: Path) -> dict[str, Any]:
    """Load and minimally validate a plan document."""
    import json

    if not path.is_file():
        raise OrchestratorError(f"plan not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OrchestratorError(f"plan is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or "tasks" not in data:
        raise OrchestratorError("plan must be an object with a 'tasks' list")
    return data
