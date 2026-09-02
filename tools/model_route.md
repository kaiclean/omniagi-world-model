# Tool: model_route

Route a request to the correct engine seat.

## Purpose
Choose a specialist and an engine seat for a task using weighted scoring, and
escalate up the ladder when confidence is low or an attempt fails.

## Inputs
- task (str): natural-language description of the work
- attempt (int, default 1) and prior failure reasons, for temporal escalation
- top_n (int, default 3): how many candidates to return

## Outputs
- `{task, specialist, seat, engine, confidence, rationale, attempt,
  cumulative_cost, escalated, exhausted, candidates[]}`

## How to invoke
- CLI: `omniagi route "implement the missing hasher" --explain`
- Python: `from omniagi.routing import route, escalate, explain`

## Dependencies
- `registry/harness.json` (routing rules and seats)

## Verification
- `omniagi route "verify the memory tool"` must select `critic`, not `coder`.
- The golden routing table in `tests/test_routing.py` locks in behaviour.
- When the ladder is exhausted the decision is marked `exhausted` and the caller
  must report a blocker rather than simulate output.
