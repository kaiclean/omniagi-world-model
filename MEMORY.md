# MEMORY.md — OmniAGI Durable World State

> Long-term memory of OmniAGI. Entries must be **durable** (still true in a
> week), **declarative** (facts, not instructions-to-self) and **compact**.
>
> Anti-staleness is no longer an honour system: every entry carries an expiry
> date and `omniagi memory` (and therefore CI) **fails** on facts that are past
> it. Correct or remove them, and log the change in `memory/CHANGELOG.md`.

## Format

Each entry is a row: `id | tag | fact | established | expires | source`.
Use `never` for structural facts that do not decay. Dates are `YYYY-MM-DD`.

**Machine-specific and personal state does not belong here.** Hostnames,
usernames, absolute home paths and storage figures go in the local memory file,
which is gitignored — `memory/local.md.example` shows the shape. The
`memory.hygiene` check enforces this.

## Entries

| id | tag | fact | established | expires | source |
|---|---|---|---|---|---|
| identity-single-master | identity | OmniAGI is the sole master of this world model harness; specialist seats are owned subroutines, never peer masters. | 2026-09-02 | never | WORLD_AGENTS.md |
| harness-source-of-truth | harness | registry/harness.json is the single source of truth for tools, agents, engine seats and routing; every markdown table describing them is generated from it. | 2026-09-02 | never | registry/harness.json |
| harness-layout | harness | Constitution lives in WORLD_AGENTS.md (not AGENTS.md, which is Hermes-protected); master spec is OmniAGI.md. | 2026-09-02 | never | WORLD_AGENTS.md |
| harness-root-resolution | harness | The harness root is resolved from the OMNIAGI_ROOT environment variable, falling back to the package parent. No module may hardcode a host path. | 2026-09-02 | never | omniagi/paths.py |
| verification-entrypoint | tooling | `omniagi check` is the read-only verification entry point; it is idempotent and must never dirty the working tree. | 2026-09-02 | never | omniagi/selfcheck.py |
| tooling-self-extension | tooling | The self-extension protocol is implemented in omniagi/extend.py and aborts before logging success if read-back verification fails. | 2026-09-02 | never | workflows/tool-extension.md |
| routing-is-scored | routing | Routing is weighted keyword scoring with unique rule priorities, a confidence value and an escalation ladder - not first-match substring scanning. | 2026-09-02 | never | omniagi/routing.py |
| engines-primary-seats | engines | Primary cloud reasoner seat is Qwen3.5-397B-A17B; coding seat is Qwen3-Coder-480B-A35B; local fallback seat is Qwen3.5-9B-HauhauCS. | 2026-09-02 | 2027-03-01 | harnesses/TOP10_AGENTIC_MOE.md |
| engines-availability-probed | engines | Seat availability is probed, never assumed; when no seat is reachable the harness reports a blocker instead of producing model output. | 2026-09-02 | never | omniagi/health.py |
| research-agentic-moe | agentic_moe | Agentic MoE research (2025-2026) converges on three axes: MoE as backbone for agentic LLMs; MoE inside agentic RL (phase-aware routing preserving temporally consistent expert specialization); and agentic routing/orchestration selecting models per step from trajectory context. Core insight: token/step-level static routing is suboptimal for agentic tasks; temporally-aware routing is strictly better. | 2026-09-02 | 2027-03-01 | references/ + prior session research |
| tooling-tool-runtime | tooling | file_read, file_write and shell execute through omniagi/tool_runtime.py with schema-validated arguments, a timeout and a JSON result; every other registered tool is specification-only and is refused at dispatch. | 2026-09-04 | never | omniagi/tool_runtime.py |
| loop-is-closed | tooling | `omniagi loop` runs the full pass - route, seat call, tool calls, verification, changelog - and marks a pass verified only when at least one tool call ran and none failed. | 2026-09-04 | never | omniagi/loop.py |
| loop-task-fixture | tooling | Loop behaviour is scored by a ten-task fixture (tests/fixtures/loop_tasks.json) replayed through the real loop by `omniagi eval`, not by grepping markdown for headings. | 2026-09-04 | never | omniagi/evaluate.py |
| engines-quarantined | engines | All ten engine seats are quarantined: their ranking is a model-catalogue claim and none has answered a request from this harness. A seat may only become active once its evidence is 'verified'. | 2026-09-04 | 2027-03-01 | docs/adr/0005-seat-quarantine.md |
| naming-harness-not-world-model | identity | This repository is an agent harness, not a world model: it routes, executes and verifies, and predicts nothing. The repository slug still says world-model. | 2026-09-04 | never | docs/adr/0004-harness-not-world-model.md |
| hermes-protected-filename | hermes | AGENTS.md is a protected filename in Hermes, so the world-model constitution lives in WORLD_AGENTS.md to stay editable by OmniAGI. | 2026-09-02 | never | WORLD_AGENTS.md |

## Update rules

- Only OmniAGI writes here (or a `memory_keeper` subroutine acting on its behalf).
- Read the current state before writing, to avoid duplicate/contradictory entries.
- When correcting a fact, append a one-liner to `memory/CHANGELOG.md`
  (`omniagi memory --log "..."` deduplicates automatically).
- Do NOT store session progress logs or TODO state here.
- Volatile host figures and endpoint status belong in the local file, not here.

## Commands

```bash
omniagi memory            # audit: expiry, hygiene, changelog duplicates
omniagi memory --list     # structured entries as JSON
omniagi memory --log "corrected engines-primary-seats"
```
