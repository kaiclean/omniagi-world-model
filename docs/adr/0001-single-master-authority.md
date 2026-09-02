# ADR 0001: Single-master authority

- Status: Accepted
- Date: 2026-09-02

## Context

The harness is self-extending: it can add tools, edit its own specifications and
amend its own instructions. A system with that power needs an unambiguous answer
to "who decides?".

Multi-agent systems that distribute authority hit two failure modes. Conflicting
instructions become resolvable in whichever direction is locally convenient — an
agent can always find *some* authority that endorses what it wanted to do. And
accountability dissolves: when every agent can amend the rules, no one is
responsible for the rules.

The original repository asserted single-master authority in prose and "enforced"
it by grepping for the phrase `sole master`. That check passed on a file that
merely mentioned the words, and would have kept passing if a second master were
added in a file that also happened to contain them.

## Decision

Exactly one entity holds master authority. Specialists execute within their
delegated scope; they do not delegate to each other and cannot amend the
constitution.

Enforcement is **structural**, not textual:

1. `registry/schema.json` fixes `role` to the constant `specialist` for every
   entry in `agents`, so a second master is rejected at load time.
2. `constitution.check_single_master` independently asserts exactly one entity
   with `role: master`, requires every agent spec to carry a subordination
   marker, and rejects any file outside the constitution that claims mastership,
   harness-wide ownership or amendment rights.
3. Negative tests inject each violation and assert the check **fails**. An
   enforcement mechanism with no failing test is theatre.

## Consequences

Adding an agent means adding a specialist. Elevating one requires editing the
schema, the invariant and the tests — three deliberate, reviewable acts, which
is the intended cost.

Layer 2 uses a pattern list (`SELF_MASTER_PATTERNS`) and can therefore produce
false positives on prose that merely discusses mastership. That is the correct
trade: a spurious failure is loud and cheap, a missed second master is silent
and expensive. Documentation that must discuss these phrases lives inside the
constitution, which is exempt by design.

## Enforcement

`constitution.check_single_master`; `tests/test_constitution.py`.
