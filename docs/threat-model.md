# Threat model — OmniAGI harness

Scope: an autonomous agent with write access to this repository and the ability
to execute commands on the host. The harness is *designed to modify itself*,
which makes several ordinary conveniences unacceptable.

## Assets

| Asset | Why it matters |
|---|---|
| The constitution (`OmniAGI.md`, `WORLD_AGENTS.md`, workflows) | Defines what the agent may do. Tampering here escalates every other permission. |
| `registry/harness.json` | Single source of truth for tools, agents and seats. Injecting a tool here grants a new capability. |
| The host shell | Arbitrary code execution. |
| Credentials (`OMNIAGI_API_KEY`, provider keys) | Cost, data exfiltration. |
| `MEMORY.md` | Poisoned memory steers all future sessions. |

## Threats and mitigations

### T1 — Command injection through the shell tool
An agent-composed string reaching a shell interpreter (`;`, `&&`, backticks,
`$()`) is arbitrary code execution.

**Mitigations.** `omniagi.shell.run` takes an *argument vector* and explicitly
rejects a bare string. `shell=True` is never used, so there is no metacharacter
interpretation. Executables are restricted to a small allowlist
(`DEFAULT_ALLOWLIST`, extendable through `OMNIAGI_SHELL_ALLOWLIST` for operators,
not for the agent). Every call has a timeout with a hard ceiling.

### T2 — Path traversal
A tool that accepts a path can be pointed at `~/.ssh/id_rsa` or
`../../etc/passwd`.

**Mitigations.** `hashing._resolve_inside_root` and `shell._validate_workdir`
resolve the path and reject anything outside the harness root. The hasher reads
only inside the harness; it never follows a caller-supplied absolute path out of
it.

### T3 — Silent constitutional drift
The most dangerous edit is the one that removes a restriction, because
afterwards nothing objects.

**Mitigations.** `memory/manifest.json` stores a SHA-256 for every constitution
file and `omniagi check` reports drift with the recorded and actual digests.
Amending the constitution requires an ADR and a deliberate manifest refresh, so
the change is visible in review rather than invisible in behaviour.

### T4 — A second master
Two masters means no master: conflicting authority is resolvable in whatever
direction is convenient.

**Mitigations.** JSON Schema rejects any agent whose `role` is not
`specialist`. Independently, `constitution.check_single_master` asserts exactly
one entity with `role: master`, requires every agent spec to carry a
subordination marker, and rejects any non-constitution file that declares
mastership, harness-wide ownership or amendment rights. Negative tests in
`tests/test_constitution.py` inject each violation and assert the check fails.

### T5 — Fabricated tool success
An agent that reports success it did not verify corrupts every downstream
decision. This is not hypothetical: the original hasher printed
`Error: File not found` and exited `0`, so CI reported a green check for a
completely broken tool.

**Mitigations.** Tools raise instead of returning sentinels;
`constitution.check_no_simulated_success` *executes* the failure path and scans
the package for `return "Error..."` patterns. When no engine seat is reachable,
`adapters.call_with_fallback` raises `SeatUnavailable` rather than returning
placeholder text.

### T6 — Credential leakage
Keys committed to the repository, or echoed into logs and traces.

**Mitigations.** Credentials are read from the environment only and never
written to disk. Run traces record commands and results, not environment
contents. `memory/local.md` (gitignored) is the documented home for host state,
and its template explicitly instructs never to store credential values. The
`memory.hygiene` check fails the build when host paths or storage figures appear
in the tracked `MEMORY.md`.

### T7 — Memory poisoning / staleness
A false "durable fact" persists indefinitely and misleads every later session.

**Mitigations.** Entries are structured rows with `established`, `expires` and
`source` columns. `omniagi memory` fails CI on expired facts and warns 30 days
ahead, so stale claims must be re-verified or removed rather than quietly
inherited.

### T8 — Supply chain
A malicious dependency or a mutated GitHub Action tag.

**Mitigations.** The harness has **zero runtime dependencies**. CI pins every
action to a full commit SHA, sets `permissions: contents: read`, and runs
`pip-audit` on the dev extras.

### T9 — Audit-trail tampering
An operator or an intruder edits, reorders, or truncates `runs/*.jsonl` to hide
what an autonomous run actually did.

**Mitigations.** Every trace event is hash-chained: it records its sequence
number, the SHA-256 `hash` of the previous event, and its own `hash` over the
remaining fields (`trace._digest`). Altering a field, deleting an event, or
swapping two lines breaks the chain. `omniagi audit` re-verifies every trace and
the `audit.trace_chain` self-check fails the build on any tampered trace found
under `runs/`.

## Explicit non-goals

- The harness does **not** sandbox the agent from the host. The allowlist raises
  the cost of a mistake; it is not a security boundary against a determined
  adversary with repository write access.
- It does not defend against a compromised CI runner or a malicious maintainer.
- It does not attempt prompt-injection defence for content fetched from the web.
  Treat `web_search` and `summarize_url` output as untrusted input.
