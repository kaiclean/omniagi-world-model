# ADR 0004: Documentation layout

- Status: Accepted
- Date: 2026-11-18

## Context

`docs/` held four documents of different kinds side by side. A task, a lookup
table and an explanation compete for the same reader attention, and readers
could not tell which to open.

## Decision

`docs/` is split into `how-to/`, `reference/` and `explanation/`, with
`docs/README.md` as the index. ADRs stay in `docs/adr/` because
`WORLD_AGENTS.md` names that path.

## Consequences

Paths of the tutorial, architecture and threat-model documents changed. The
registry (`registry/harness.json`) referenced two of them, so `TOOLS.md` was
regenerated and its manifest entry deliberately refreshed.

## Enforcement

`omniagi check` resolves every relative markdown link; `omniagi docs --check`
fails when generated blocks are stale.
