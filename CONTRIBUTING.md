# Contributing to the OmniAGI world model

The harness has exactly one rule that matters: **every claim must be
machine-checkable**. If you add a capability, add the check that proves it
works, and make CI fail when it stops working.

## Setup

```bash
python3 -m pip install -e ".[dev]"
pre-commit install     # optional but recommended
```

The harness itself has **no runtime dependencies** — it runs on the standard
library so a fresh checkout can be verified anywhere.

## The one command you need

```bash
omniagi check          # read-only verification of the whole harness
```

`omniagi check` is idempotent and never writes to your working tree. If it
leaves a dirty diff, that is a bug.

## Golden rules

1. **`registry/harness.json` is the single source of truth.** Tools, agents,
   engine seats and routing rules live there and nowhere else.
2. **Never hand-edit a generated markdown block.** Anything between
   `<!-- omniagi:generated:start ... -->` and the matching `end` marker is a
   build artifact. Edit the registry, then run `omniagi docs`.
3. **Never simulate success.** A tool that cannot do its job must raise or exit
   non-zero. Returning `"Error: ..."` as a value is how a broken tool passed CI
   for weeks.
4. **Never add a second master.** Specialists are subordinate subroutines.
   `omniagi check` enforces this structurally and there is a negative test that
   proves the enforcement actually fails.

## Adding a tool

Use the protocol rather than editing files by hand:

```bash
omniagi extend my_new_tool --purpose "what it does" --script omniagi/my_new_tool.py
```

That writes the spec, registers it, regenerates every derived table, verifies by
read-back and appends a deduplicated changelog line. The long-form walkthrough is
in `docs/tutorial-add-a-tool.md`.

## Changing the constitution

Constitutional changes need an ADR in `docs/adr/`. Record *why*, not just what —
a rule whose rationale is lost gets deleted by the next person who finds it
inconvenient. After changing any constitution file, refresh the hash manifest:

```bash
omniagi hash --write-manifest
```

## Changing engine seats

Every seat needs provenance: `source`, `benchmark`, `measured_on`, `verified_on`
and a `confidence` tier (`verified` = we ran it, `cited` = someone else measured
it, `estimated` = vendor claim or inference). `omniagi check` warns when the
evidence goes stale.

## Before you push

```bash
ruff check . && ruff format --check .
mypy
pytest
omniagi check
omniagi docs --check
git status --short       # must be empty
```

CI runs exactly these on Ubuntu and macOS across Python 3.10–3.13.
