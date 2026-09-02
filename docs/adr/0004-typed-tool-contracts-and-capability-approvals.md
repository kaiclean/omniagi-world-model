# ADR 0004: Typed tool contracts and capability approvals

- Status: Accepted
- Date: 2026-09-02

## Context

Tools are the harness's hands. Two questions were previously answered only in
prose: *what does a tool accept and return*, and *who is allowed to invoke it*.

A tool spec described its arguments in English, so nothing stopped a caller from
passing the wrong shape and nothing stopped a low-trust caller from invoking a
destructive tool. The registry already tagged each tool with a `capabilities`
list (`fs_write`, `process_exec`, `network`, `registry_write`, ...), but those
tags were documentation, not a gate.

## Decision

The registry carries two machine-checked layers over every tool.

1. **Typed contracts.** Each active tool declares a `contract` with a `summary`,
   typed `inputs`, typed `outputs` and named `errors`. `omniagi/contracts.py`
   validates arguments against the declared inputs and fails the build when a
   contract is malformed (unknown type, duplicate field, missing summary).
2. **Capability approvals.** `registry.policies` maps each capability to a risk
   and an approval level. `omniagi/policy.py` refuses to let a high-risk
   capability resolve to automatic approval, so `fs_write`, `process_exec`,
   `network` and `registry_write` always require the registered authority.

Both are ordinary named checks in `selfcheck.run_checks`, so they run on every
`omniagi check` and in CI.

## Consequences

Adding a tool now means declaring its contract and its capabilities. A tool that
appends itself through the self-extension protocol without a contract is graded
a **warning**, not a hard failure, so extension stays possible while the gap is
visible; a *malformed* contract fails immediately.

Contract types are intentionally a small, closed vocabulary (`string`, `integer`,
`number`, `boolean`, `object`, `array`, `null`). Richer schemas were rejected as
scope the harness does not yet need.

## Enforcement

`contracts.check_tool_contracts`, `policy.check_capability_approvals`;
`tests/test_contracts.py`, `tests/test_policy.py`.
