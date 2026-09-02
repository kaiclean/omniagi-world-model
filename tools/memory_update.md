# Tool: memory_update

Update durable memory and the changelog.

## Purpose
Keep `MEMORY.md` correct and non-stale, and keep `memory/CHANGELOG.md` free of
the duplicate spam that an unguarded append-only log accumulates.

## Inputs
- message (str) for a changelog entry, or an edit to the `MEMORY.md` entry table

## Outputs
- audit results: expiry, hygiene and changelog duplication

## How to invoke
- CLI: `omniagi memory` (audit), `omniagi memory --list`,
  `omniagi memory --log "<message>"`, `omniagi memory --dedupe`
- Python: `from omniagi.memory import append_changelog, parse_memory`

## Dependencies
- none

## Verification
- `omniagi memory` fails when any entry is past its `expires` date.
- Appending an entry identical to the previous one is skipped, not duplicated.
- Machine-specific state in `MEMORY.md` fails the `memory.hygiene` check.
