# ADR 0002: Registry as single source of truth

- Status: Accepted
- Date: 2026-09-02

## Context

The tool list previously existed in `TOOLS.md`, `references/tools-registry.md`
and the individual `tools/*.md` specs. They had already diverged: the registry
listed eleven tools, the reference table listed ten, and one spec existed with
no registration anywhere.

This is the predictable outcome of storing the same fact in three
human-maintained places. No amount of discipline fixes it, because the failure
is silent — nothing breaks when the copies disagree, they just quietly stop
meaning anything.

Reconciling the copies by hand was rejected: it fixes today's drift and
guarantees tomorrow's.

## Decision

`registry/harness.json` is the sole authority for tools, agents, engine seats,
routing rules and non-negotiables. It is validated by `registry/schema.json`.

Every table describing that data is a **build artifact**, rendered by
`omniagi.docgen` into explicitly marked regions:

```
<!-- omniagi:generated:start id=tools-table -->
...generated, do not edit...
<!-- omniagi:generated:end id=tools-table -->
```

`omniagi docs --check` fails CI when a generated block does not match what the
registry would produce. Prose outside the markers stays hand-written, because
rationale is exactly what generation cannot supply.

JSON was chosen over YAML solely so the harness keeps zero runtime
dependencies; `jsonschema` is optional and referential integrity is checked with
the standard library regardless.

## Consequences

Adding a tool is a one-command change (`omniagi extend`) rather than four
coordinated hand edits. Divergence is now structurally impossible rather than
merely discouraged.

The cost: contributors must not edit generated regions, and a docs change
requires a regeneration step. The `--check` mode makes forgetting it a loud CI
failure rather than a slow rot.

## Enforcement

`docgen.check_docs`; `integrity.check_tool_registry` and
`integrity.check_agent_registry`; `tests/test_registry_and_integrity.py`.
