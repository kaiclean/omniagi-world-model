"""Autonomous run-lifecycle tests."""

from __future__ import annotations

import json

import pytest

from omniagi import orchestrator
from omniagi.orchestrator import Budget, Orchestrator, OrchestratorError, Outcome


def _plan(*tasks: dict) -> dict:
    return {"goal": "test", "tasks": list(tasks)}


def _ok_executor(reason: str = "ok"):
    def executor(task, decision, registry) -> Outcome:
        return Outcome(ok=True, reason=reason, evidence={"task": task.id}, observation=reason)

    return executor


def test_linear_dag_completes(temp_harness, registry) -> None:
    plan = _plan(
        {"id": "a", "description": "first", "kind": "x", "depends_on": []},
        {"id": "b", "description": "second", "kind": "x", "depends_on": ["a"]},
    )
    orch = Orchestrator.from_plan(
        plan, run_id="r1", registry=registry, executors={"x": _ok_executor()}
    )
    state = orch.run()
    assert state.status == "completed"
    assert [t.state for t in state.tasks] == ["done", "done"]
    assert state.spent_steps == 2


def test_checkpoint_is_written(temp_harness, registry) -> None:
    plan = _plan({"id": "a", "description": "x", "kind": "x", "depends_on": []})
    orch = Orchestrator.from_plan(
        plan, run_id="rc", registry=registry, executors={"x": _ok_executor()}
    )
    orch.run()
    assert orch.checkpoint_path.is_file()
    saved = json.loads(orch.checkpoint_path.read_text())
    assert saved["status"] == "completed"


def test_resume_skips_completed_tasks(temp_harness, registry) -> None:
    calls: list[str] = []

    def counting(task, decision, registry) -> Outcome:
        calls.append(task.id)
        return Outcome(ok=True, reason="ok")

    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": []},
        {"id": "b", "description": "x", "kind": "x", "depends_on": ["a"]},
    )
    Orchestrator.from_plan(
        plan, run_id="rr", registry=registry, executors={"x": counting}
    ).run()
    assert calls == ["a", "b"]

    resumed = Orchestrator.resume("rr", registry=registry, executors={"x": counting})
    resumed.run()
    # No task re-executed on resume: the completed run does nothing.
    assert calls == ["a", "b"]


def test_failed_task_blocks_dependents(temp_harness, registry) -> None:
    def fail(task, decision, registry) -> Outcome:
        return Outcome(ok=False, reason="nope", retryable=False)

    plan = _plan(
        {"id": "a", "description": "x", "kind": "fail", "depends_on": []},
        {"id": "b", "description": "x", "kind": "ok", "depends_on": ["a"]},
    )
    orch = Orchestrator.from_plan(
        plan,
        run_id="rf",
        registry=registry,
        executors={"fail": fail, "ok": _ok_executor()},
    )
    state = orch.run()
    assert state.task("a").state == "failed"
    assert state.task("b").state == "blocked"
    assert state.status == "failed"


def test_blocked_model_seat_is_reported(temp_harness, registry) -> None:
    def blocked(task, decision, registry) -> Outcome:
        return Outcome(ok=False, reason="no credentials", blocked=True)

    plan = _plan({"id": "m", "description": "call a model", "kind": "model", "depends_on": []})
    orch = Orchestrator.from_plan(
        plan, run_id="rb", registry=registry, executors={"model": blocked}
    )
    state = orch.run()
    assert state.task("m").state == "blocked"
    assert any("no credentials" in blocker for blocker in state.blockers)
    assert state.status == "blocked"


def test_retries_then_succeeds_with_escalation(temp_harness, registry) -> None:
    seats_used: list[str] = []

    def flaky(task, decision, registry) -> Outcome:
        seats_used.append(decision.seat)
        if len(seats_used) < 3:
            return Outcome(ok=False, reason="transient", retryable=True)
        return Outcome(ok=True, reason="recovered")

    plan = _plan({"id": "a", "description": "flaky task", "kind": "f", "depends_on": []})
    orch = Orchestrator.from_plan(
        plan,
        run_id="rt",
        registry=registry,
        budget=Budget(max_steps=64, max_seconds=900, max_retries=5, max_cost=1000),
        executors={"f": flaky},
    )
    state = orch.run()
    assert state.task("a").state == "done"
    assert len(state.task("a").attempts) == 3
    # Escalation climbs the ladder, so later attempts may use a different seat.
    assert len(seats_used) == 3


def test_retry_budget_is_enforced(temp_harness, registry) -> None:
    def always_fail(task, decision, registry) -> Outcome:
        return Outcome(ok=False, reason="always", retryable=True)

    plan = _plan({"id": "a", "description": "x", "kind": "f", "depends_on": []})
    orch = Orchestrator.from_plan(
        plan,
        run_id="rmax",
        registry=registry,
        budget=Budget(max_steps=64, max_seconds=900, max_retries=2, max_cost=1000),
        executors={"f": always_fail},
    )
    state = orch.run()
    assert state.task("a").state == "failed"
    # max_retries=2 → attempts 1, 2, 3 (initial + 2 retries).
    assert len(state.task("a").attempts) == 3


def test_step_budget_halts_run(temp_harness, registry) -> None:
    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": []},
        {"id": "b", "description": "x", "kind": "x", "depends_on": ["a"]},
        {"id": "c", "description": "x", "kind": "x", "depends_on": ["b"]},
    )
    orch = Orchestrator.from_plan(
        plan,
        run_id="rs",
        registry=registry,
        budget=Budget(max_steps=2, max_seconds=900, max_retries=3, max_cost=1000),
        executors={"x": _ok_executor()},
    )
    state = orch.run()
    assert state.status == "exhausted"
    assert state.spent_steps == 2
    assert any("step budget" in blocker for blocker in state.blockers)


def test_time_budget_halts_run(temp_harness, registry) -> None:
    ticks = iter([0.0, 0.0, 100.0, 200.0, 300.0, 400.0])

    def clock() -> float:
        return next(ticks)

    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": []},
        {"id": "b", "description": "x", "kind": "x", "depends_on": ["a"]},
    )
    orch = Orchestrator.from_plan(
        plan,
        run_id="rtime",
        registry=registry,
        budget=Budget(max_steps=64, max_seconds=50, max_retries=3, max_cost=1000),
        executors={"x": _ok_executor()},
        clock=clock,
    )
    state = orch.run()
    assert state.status == "exhausted"
    assert any("time budget" in blocker for blocker in state.blockers)


def test_cost_budget_halts_run(temp_harness, registry) -> None:
    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": []},
        {"id": "b", "description": "x", "kind": "x", "depends_on": ["a"]},
    )
    orch = Orchestrator.from_plan(
        plan,
        run_id="rcost",
        registry=registry,
        budget=Budget(max_steps=64, max_seconds=900, max_retries=3, max_cost=0.0),
        executors={"x": _ok_executor()},
    )
    state = orch.run()
    assert state.status == "exhausted"
    assert any("cost budget" in blocker for blocker in state.blockers)


def test_unknown_kind_fails_task(temp_harness, registry) -> None:
    plan = _plan({"id": "a", "description": "x", "kind": "ghost", "depends_on": []})
    orch = Orchestrator.from_plan(plan, run_id="rg", registry=registry, executors={})
    state = orch.run()
    assert state.task("a").state == "failed"
    assert any("no executor" in blocker for blocker in state.blockers)


def test_critic_rejects_short_model_output(temp_harness, registry) -> None:
    def tiny(task, decision, registry) -> Outcome:
        return Outcome(ok=True, reason="ok", evidence={"content": ""}, retryable=False)

    plan = _plan(
        {
            "id": "m",
            "description": "x",
            "kind": "model",
            "depends_on": [],
            "params": {"min_chars": 5},
        }
    )
    orch = Orchestrator.from_plan(
        plan, run_id="rcrit", registry=registry, executors={"model": tiny}
    )
    state = orch.run()
    assert state.task("m").state == "failed"
    assert "too short" in state.task("m").attempts[-1].reason


def test_duplicate_ids_are_rejected(registry) -> None:
    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": []},
        {"id": "a", "description": "y", "kind": "x", "depends_on": []},
    )
    with pytest.raises(OrchestratorError, match="duplicate task ids"):
        Orchestrator.from_plan(plan, run_id="d", registry=registry)


def test_unknown_dependency_is_rejected(registry) -> None:
    plan = _plan({"id": "a", "description": "x", "kind": "x", "depends_on": ["ghost"]})
    with pytest.raises(OrchestratorError, match="unknown task"):
        Orchestrator.from_plan(plan, run_id="u", registry=registry)


def test_cycle_is_rejected(registry) -> None:
    plan = _plan(
        {"id": "a", "description": "x", "kind": "x", "depends_on": ["b"]},
        {"id": "b", "description": "x", "kind": "x", "depends_on": ["a"]},
    )
    with pytest.raises(OrchestratorError, match="cycle"):
        Orchestrator.from_plan(plan, run_id="c", registry=registry)


def test_empty_plan_is_rejected(registry) -> None:
    with pytest.raises(OrchestratorError, match="no tasks"):
        Orchestrator.from_plan({"tasks": []}, run_id="e", registry=registry)


def test_load_plan_validates(temp_harness) -> None:
    path = temp_harness / "plan.json"
    path.write_text('{"nope": 1}', encoding="utf-8")
    with pytest.raises(OrchestratorError, match="must be an object with a 'tasks'"):
        orchestrator.load_plan(path)


def test_default_verify_task_uses_real_selfcheck(temp_harness, registry) -> None:
    plan = _plan({"id": "v", "description": "verify", "kind": "verify", "depends_on": []})
    orch = Orchestrator.from_plan(plan, run_id="rv", registry=registry)
    state = orch.run()
    assert state.task("v").state == "done"
    assert "passed" in state.task("v").evidence


def test_sample_plan_runs(temp_harness, repo_root, registry) -> None:
    plan = orchestrator.load_plan(repo_root / "plans" / "self-verify.json")
    orch = Orchestrator.from_plan(plan, run_id="sample", registry=registry)
    state = orch.run()
    assert state.status == "completed"
