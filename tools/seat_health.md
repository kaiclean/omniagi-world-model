# Tool: seat_health

Probe engine-seat availability so "cloud down → local fallback" is an executed
decision rather than documented intent.

## Purpose
Determine which engine seats are actually usable right now. Absence of evidence
is never treated as availability.

## Inputs
- probe_network (bool, default false): when false, only credentials and
  configuration are inspected so CI stays offline and deterministic.

## Outputs
- list of `{seat, engine, tier, available, reason}` records. `reason` is always
  populated, including for unavailable seats.

## How to invoke
- CLI: `omniagi seats [--probe-network]`
- Python: `from omniagi.health import probe_all, select_available_seat`

## Dependencies
- none (standard library sockets)
- optional: `OMNIAGI_API_KEY` / `OPENAI_API_KEY` for cloud seats,
  `OMNIAGI_LOCAL_ENDPOINTS` to override local endpoints

## Verification
- Run `omniagi seats` with no credentials set: every cloud seat must report
  `available: false` with a reason naming the missing variable.
- `select_available_seat` returns `None` when nothing is reachable, and callers
  must then report a blocker rather than produce model output.
