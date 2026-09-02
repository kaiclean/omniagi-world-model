# Architecture

## The inversion

The harness used to be prose-first: markdown was the source of truth and Python
was a thin illustration of it. Nothing was verifiable, so everything drifted —
the tool list existed in three places and already disagreed with itself.

It is now registry-first. One machine-readable file describes the world, code
derives everything else from it, and CI enforces the correspondence.

```
                    registry/harness.json
                 (master, agents, tools, seats,
                  routing rules, non-negotiables)
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   docgen.py            routing.py           integrity.py
        │                    │                    │
  generated tables      decisions +         registry ↔ filesystem
  in TOOLS.md,          escalation          reconciliation,
  WORLD_AGENTS.md,           │              link + path checks
  references/,               │                    │
  workflows/            health.py                 │
        │              (seat probing)             │
        └────────────────────┼────────────────────┘
                             │
                       selfcheck.py
                (runs every named check, read-only)
                             │
              ┌──────────────┴──────────────┐
              │                             │
         omniagi check                 watchdog.py
         (CI + humans)            (periodic, backoff, alerts)
```

## Layers

| Layer | Modules | Responsibility |
|---|---|---|
| Foundation | `paths`, `results` | Portable root resolution; the `CheckResult` type every check returns. |
| Truth | `registry` | Load and validate `registry/harness.json` (schema + referential integrity). |
| Derivation | `docgen` | Render registry data into marked markdown blocks; detect staleness. |
| Verification | `integrity`, `constitution`, `hashing`, `memory` | Named checks over real filesystem state. |
| Decision | `routing`, `health` | Which specialist, which seat, is it reachable. |
| Execution | `shell`, `extend`, `adapters` | Bounded side effects. |
| Observation | `trace`, `watchdog`, `bench` | Tamper-evident hash-chained JSONL run traces; periodic health enforcement (see [deploy/](../deploy/README.md)); offline evaluation suites (see [benchmarks/](../benchmarks/README.md)). |
| Surface | `cli` | `omniagi <check\|route\|run\|hash\|docs\|extend\|memory\|world\|watch\|seats\|audit\|bench>`. |

## Data flow: routing a task

1. `cli.route` parses the task and builds a `RoutingContext` (attempt number,
   cumulative cost, prior failures).
2. `routing.score_task` tokenises the task and scores every rule by summing
   matched keyword weights; unique rule priorities break ties deterministically.
3. `routing.confidence_of` combines evidence **strength**, the winner's
   **share**, and its **margin** over the runner-up.
4. Below the confidence threshold, the decision starts at the cheapest ladder
   seat. After a failure, `escalate` climbs and accumulates cost.
5. `health.select_available_seat` probes reachability. If nothing is reachable
   the caller receives `None`/`SeatUnavailable` and must report a blocker.
6. `trace.Trace` appends the decision to `runs/<date>-<id>.jsonl`. Each event
   carries the SHA-256 `hash` of the previous one, so `omniagi audit` can later
   prove the trace was not edited, reordered, or truncated.

## Invariants CI enforces

1. Exactly one master, structurally — with negative tests proving the check
   fails when a second is injected.
2. Generated markdown matches the registry.
3. Every registered tool has a spec; every spec is registered; every referenced
   script exists.
4. Constitution file hashes match `memory/manifest.json`.
5. No source file hardcodes a host path.
6. No durable memory entry is past its expiry.
7. Every relative markdown reference resolves, or is an exemption *with a
   documented reason*.
8. Tools fail loudly — no error sentinels returned as values.
9. Every active tool declares a well-formed typed contract (inputs, outputs,
   errors); high-risk capabilities never auto-approve.
10. Recorded world-state facts are type-checked and carry provenance; a
    lower-confidence claim never silently overwrites a higher-confidence one.
11. Run traces are a tamper-evident hash chain — editing, reordering or
    truncating a trace fails `audit.trace_chain`.

## Design decisions worth knowing

**Zero runtime dependencies.** A fresh checkout can be fully verified with only
the standard library. `jsonschema` is optional; without it the referential
integrity rules still run.

**Checks return data, not exit codes.** Every check yields a `CheckResult` with
a name, so a CI failure says `constitution.single_master` rather than
`RESULT: FAIL`.

**Verification never mutates.** `omniagi check` is idempotent. The mutating
self-extension demo runs in a temporary harness copy. If `omniagi check` leaves
a dirty tree, that is a bug.

**Escalation is stateful.** Routing is not a pure function of the prompt; the
third attempt at a task must not return to the cheapest seat.
