# ADR 0007: Typed world-state memory with provenance

- Status: Accepted
- Date: 2026-09-02

## Context

Durable memory in `MEMORY.md` is prose maintained by hand: excellent for humans,
but not a structure a run loop can safely read or write mid-task. A world model
needs a machine-readable store of facts it can assert during a run — and the
moment two runs assert different values for the same fact, it needs a rule for
who wins that is not "whoever wrote last".

Memory poisoning (ADR/threat T7) is the failure this must resist: a confident,
unsourced claim silently overwriting a better one and misleading every later
session.

## Decision

`omniagi/worldstate.py` maintains a typed key/value store at
`memory/world-state.json` (gitignored runtime state).

- **Typed.** Each fact declares a type; `assert_fact` rejects a value that does
  not match, so the store cannot drift into garbage.
- **Provenance.** Every fact carries its `source`, a timestamp and a
  `confidence` in `[0, 1]`.
- **Conflict resolution.** Re-asserting the same value keeps the higher
  confidence and records no conflict. A *different* value wins only if its
  confidence is strictly higher, and the superseded fact is archived to a
  history log; a lower- or equal-confidence contradiction is rejected and the
  rejection is archived. Nothing is ever overwritten silently.

`worldstate.check_world_state` validates the store during `omniagi check`; an
absent store is a pass ("no world state recorded yet").

## Consequences

The store is deliberately separate from `MEMORY.md`: the constitution's durable
facts remain human-curated and hash-manifested, while world-state is runtime
scratch memory with its own provenance rules. Confidence is a blunt instrument —
it does not model source reliability over time — but it is enough to make the
overwrite rule safe and auditable, and the history log preserves what a more
sophisticated policy would need later.

## Enforcement

`worldstate.assert_fact`, `worldstate.check_world_state`;
`tests/test_worldstate.py`.
