# CLI and configuration reference

## Commands

Entry point: `omniagi` (`omniagi/cli.py`). Run `omniagi <command> --help` for flags.

| Command | Effect |
|---|---|
| `check` | Run every named check, read-only. Flags: `--json`, `--verbose`, `--probe-network`, `--strict`. |
| `route <task>` | Print the routing decision; `--explain` for reasoning, `--attempt`, `--failed`, `--top`. |
| `hash [path]` | SHA-256 of a harness file; `--write-manifest`, `--verify-manifest`. |
| `docs` | Regenerate registry-derived blocks; `--check` fails when stale. |
| `extend [tool_id]` | Self-extension protocol. Needs `--approve`; `--demo` runs in a temporary copy. |
| `memory` | Audit memory; `--list`, `--dedupe`, `--log MESSAGE`. |
| `watch` | Watchdog; `--once`, `--strict`, `--interval`, `--max-backoff`, `--json`. |
| `seats` | Probe engine-seat availability; `--probe-network`. |

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `OMNIAGI_ROOT` | `omniagi/paths.py` | Harness root; defaults to the checkout. |
| `OMNIAGI_BASE_URL` | `omniagi/adapters.py` | OpenAI-compatible endpoint for seat calls. |
| `OMNIAGI_API_KEY` | `omniagi/adapters.py`, `omniagi/health.py` | Credential for seat calls (`OPENAI_API_KEY` and `OPENROUTER_API_KEY` are also read). |
| `OMNIAGI_MAX_SEAT_CALLS` | `omniagi/adapters.py` | Per-process seat-call budget; default 20, `0` disables calls. |
| `OMNIAGI_LOCAL_ENDPOINTS` | `omniagi/health.py` | Comma-separated local inference endpoints to probe. |
| `OMNIAGI_SHELL_ALLOWLIST` | `omniagi/shell.py` | Extra executables an operator permits for the shell tool. |
| `OMNIAGI_NO_TRACE` | `omniagi/trace.py` | Set to disable JSONL run traces. |
| `OMNIAGI_LIVE_SEAT_TEST` | `tests/test_adapters.py` | Opt in to the live seat test. |

## Approval flags

Actions with effect beyond the harness need an explicit decision: `omniagi extend --approve`,
`shell.run(..., approved=True)`, and `approved=True` for writes outside the harness root.
