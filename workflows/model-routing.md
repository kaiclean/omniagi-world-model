# Workflow: Model Routing

> How OmniAGI picks an engine seat for a request.
> The routing table below is generated from `registry/harness.json` — edit the
> registry, then run `omniagi docs`.

## Routing is scored, not first-match

Routing used to be first-match substring scanning, which sent
`"verify the memory tool"` to the **coder** because the string `tool` appeared.
It is now weighted scoring:

1. The task is tokenised (with light suffix normalisation, so `tools` matches `tool`).
2. Each rule sums the weights of its matched keywords.
3. Ties break on the rule's unique `priority`.
4. Confidence combines the winner's share of total evidence with its margin over
   the runner-up, so two equally strong matches yield *low* confidence.

```bash
omniagi route "verify the memory tool" --explain
```

<!-- omniagi:generated:start id=routing-table -->
| Priority | Specialist | Engine seat | Top weighted signals |
|---|---|---|---|
| 10 | `critic` | DeepSeek-V3.1 / R1 | audit (5), critique (5), double-check (5), verification (5), verify (5), confirm (4) |
| 20 | `coder` | Qwen3-Coder-480B-A35B-Instruct | debug (5), implement (5), refactor (5), bug (4), code (4), compile (4) |
| 30 | `reasoner` | Qwen3.5-397B-A17B | architecture (5), design (5), plan (5), strategy (5), analyze (4), decompose (4) |
| 40 | `memory_keeper` | Qwen3.5-122B-A10B | consolidate (5), recall (5), remember (5), changelog (4), forget (4), memory (4) |
| 50 | `scout` | Qwen3.6-35B-A3B | grep (5), look up (5), lookup (5), retrieve (5), scout (5), search (5) |
| — | `router` (default) | Qwen3.5-122B-A10B | no strong specialist signal |
<!-- omniagi:generated:end id=routing-table -->

## Escalation ladder (temporally-aware routing)

`MEMORY.md` records that step-level *static* routing is strictly worse than
temporally-aware routing for agentic work. The ladder implements that: start
cheap when confidence is low, and climb on failure while carrying attempt count
and cumulative cost.

<!-- omniagi:generated:start id=escalation-ladder -->
Escalate when routing confidence < 0.45 or a step fails, up to 3 attempts:

1. Qwen3.6-35B-A3B (relative cost 1.0)
2. Qwen3.5-122B-A10B (relative cost 3.0)
3. Qwen3.5-397B-A17B (relative cost 8.0)
<!-- omniagi:generated:end id=escalation-ladder -->

```bash
omniagi route "refactor the dispatcher" --failed "seat timed out" --explain
```

## Routing rules

1. Probe seat availability (`omniagi seats`) — never assume a seat is up.
2. If no cloud seat is reachable → local fallback, if the local endpoint answers.
3. If neither → **report a blocker; do NOT simulate model output.**
   `omniagi.adapters.call_with_fallback` raises `SeatUnavailable` here by design.
4. Only OmniAGI may change routing, and the change is a registry edit plus
   `omniagi docs`, logged in `memory/CHANGELOG.md`.
5. Specialist subroutines inherit routing; they cannot permanently own a seat.

## How to call a seat

`omniagi/adapters.py` is the reference implementation: an OpenAI-compatible
chat-completions call keyed on `OMNIAGI_BASE_URL` plus an API key environment
variable. It always sends a system prompt identifying as OmniAGI operating under
`OmniAGI.md`, and it raises instead of returning placeholder content.
