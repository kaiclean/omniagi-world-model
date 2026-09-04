# ADR 0005: Tamper-evident run traces

- Status: Accepted
- Date: 2026-09-02

## Context

Every CLI invocation already wrote a JSONL trace under `runs/` so an agent loop
could be reconstructed after the fact. But an append-only text file is only as
trustworthy as everyone who can write to it: an operator, a buggy tool, or an
intruder could edit a decision, delete an inconvenient event, or reorder the log
to tell a different story, and nothing would notice.

An audit trail that can be silently rewritten is not evidence.

## Decision

Trace events are chained with SHA-256. Each record carries its sequence number,
the hash of the previous event (`prev`, seeded from a fixed genesis value), and
its own `hash` computed over the rest of the record (`trace._digest`). The chain
makes tampering self-evident:

- altering any field changes that event's recomputed hash;
- deleting or inserting an event breaks the `prev` link and the sequence;
- reordering events breaks both.

`omniagi audit` re-verifies any trace file, and `audit.trace_chain` is a named
check in `omniagi check`. Because `runs/` is gitignored and often empty, an
absent or empty trace directory is a **pass** ("nothing to audit"); a present
but tampered trace is a **failure**.

## Consequences

The chain proves *integrity*, not *confidentiality* — it shows a trace was not
edited after the fact, not that its author was honest at write time. It also does
not prevent deleting the whole file; it guarantees that whatever remains is
internally consistent or visibly broken.

Traces still record commands and results, never environment contents, so
hash-chaining them does not widen the credential-leak surface (see the threat
model, T6/T9).

## Enforcement

`trace.audit_trace`, `selfcheck._check_trace_chain`; `tests/test_audit.py`,
`tests/test_health_watchdog.py`.
