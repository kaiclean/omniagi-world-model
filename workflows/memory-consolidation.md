# Workflow: Memory Consolidation

> Keeps MEMORY.md durable, correct, and non-stale.

## When to run
- After a task changes a durable fact (engine seat, routing, harness layout, machine state).
- When an existing MEMORY.md entry is discovered to be wrong or expired.
- At the end of a major phase, before the final verification report.

## Steps
1. Read `MEMORY.md` fully.
2. For each entry, ask: still true? still useful? still compact?
3. If wrong/expired → correct or remove; append a one-liner to `memory/CHANGELOG.md`.
4. If new durable fact was established → add a declarative line under the right tag.
5. Do NOT add session progress logs / TODO state here.
6. Verify by reading MEMORY.md back after the write.

## Anti-staleness rules
- Machine disk free figures expire fast → only record the date, not the number, unless it's structural.
- "Currently DOWN" status for endpoints → record date only; re-check before relying on it.
- Engine seat rankings can change → always keep a dated "evidence date" in harnesses/.