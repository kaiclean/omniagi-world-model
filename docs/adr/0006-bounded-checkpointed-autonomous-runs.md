# ADR 0006: Bounded, checkpointed autonomous runs

- Status: Accepted
- Date: 2026-09-02

## Context

`omniagi route` answers "which specialist and seat for this one task". It says
nothing about executing a *goal* made of many dependent tasks: how to order
them, when to stop, what to do when a step fails, and how to survive a crash
without redoing everything.

An autonomous loop without explicit bounds is the classic runaway-agent failure:
it burns budget, retries forever, and leaves no resumable state.

## Decision

`omniagi run` executes a plan as a bounded, checkpointed task DAG
(`omniagi/orchestrator.py`).

- **Plan.** A goal plus tasks, each with `id`, `kind`, `depends_on` and
  `params`. Cycles and dangling dependencies are rejected before execution.
- **Budgets.** Steps, wall-clock seconds, per-task retries and cumulative cost
  are drawn from `registry.default_budget()` and overridable per run. Exhaustion
  stops the run and is reported as a blocker, never smoothed over.
- **Route → execute → critique.** Each task is routed, executed, then judged by
  a critic. A retryable rejection escalates the engine seat and retries within
  budget; a task that reports a genuine blocker (for example, no reachable model
  seat offline) is marked `blocked`, not retried into the ground.
- **Checkpoints.** State is written atomically to `runs/<run_id>/state.json`
  after each task, so `--resume` continues exactly where a run stopped.
- **Evidence.** Attempts, observations and outcomes are recorded, and run/task
  events are emitted into the same tamper-evident trace as the rest of the CLI.

## Consequences

The default executors are deliberately offline-safe: `verify` runs the harness
self-check, `route` produces a routing decision, `noop` records a note, and
`model` calls a real seat — reporting a blocker when none is reachable rather
than fabricating output. This keeps `omniagi run` deterministic and testable
without credentials while leaving a real model path for when seats exist.

Final status has a fixed precedence: budget-exhausted over failed over blocked
over completed, so a run never reports success while it was actually starved.

## Enforcement

`orchestrator.Orchestrator`, `registry.default_budget`;
`tests/test_orchestrator.py`, `plans/self-verify.json`.
