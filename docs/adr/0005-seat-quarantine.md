# ADR 0005: Engine seats are quarantined until they are actually called

- Status: Accepted
- Date: 2026-09-04

## Context

`harnesses/TOP10_AGENTIC_MOE.md` ranked ten engines, led by a 397B-parameter
seat, with provenance recorded as "catalogue capability flags". No seat in that
table had ever answered a request from this harness. The routing table, the
escalation ladder and the cost model were all built on a list nobody had
exercised — a ranking of engines by hearsay, presented with the same
confidence as a measured result.

The adapter itself *is* exercised: `tests/test_adapters.py` runs the full
request/response cycle against a stub OpenAI-compatible server on localhost,
on by default, no network and no credentials required. So the transport is
proven. The seats are not.

## Decision

Every seat carries `status` in the registry: `active` or `quarantined`.

* A quarantined seat is reported unavailable by `health.probe_seat` (with the
  reason stated) and refused by `adapters.call_seat`. The loop therefore
  reports a blocker instead of routing work to an unproven engine.
* A seat may only be set `active` when its `confidence` is `verified` — that
  is, when someone has called it against a real endpoint and recorded the
  result. `evidence.seat_quarantine` **fails** the self-check if an active seat
  is backed by anything weaker.
* Deliberately exercising the transport against a quarantined seat requires an
  explicit opt-in: `allow_quarantined=True`, or
  `OMNIAGI_ALLOW_QUARANTINED_SEATS=1` for an operator who accepts that the
  ranking is unverified. The opt-in is auditable; a silent default would not be.

All ten seats ship quarantined, because none of them has been called.

## Consequences

Out of the box the harness cannot make a model call. That is the honest state
of affairs: it could not make a *trustworthy* one before either, it just did
not say so. Everything that does not require a seat — the tool runtime, the
router, the checks, the fixture — runs offline and green.

## Enforcement

`evidence.seat_quarantine` in `omniagi/selfcheck.py`; `health.probe_seat`;
`adapters.call_seat`; `tests/test_adapters.py`; `tests/test_health_watchdog.py`.
