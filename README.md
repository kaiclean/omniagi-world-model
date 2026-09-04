# OmniAGI Harness

A single-master, self-extending **agent harness** — where every claim about the
system is checked by code rather than asserted in prose.

> **Naming.** This is a harness, not a world model: it routes tasks, runs tools
> and verifies outcomes. It does not predict the next state of anything. The
> repository slug still says `world-model`; the artefact does not
> ([ADR 0004](docs/adr/0004-harness-not-world-model.md)).

> Exactly **one** master: **OmniAGI**. Top-10 MoE/agentic engines are owned
> seats, not peer AGIs. That is not a slogan; it is
> [an enforced structural invariant](docs/adr/0001-single-master-authority.md)
> with tests that prove the check fails when a second master is injected.

## Quick start

```bash
python3 -m pip install -e ".[dev]"

omniagi check                        # verify the harness (read-only, idempotent)
omniagi route "fix the failing test" --explain
omniagi tool list                    # tools that actually run, with their schemas
omniagi tool run file_read --args '{"path": "LICENSE"}'
omniagi eval                         # score the 10-task behavioural fixture
omniagi extend --demo                # real self-extension, in a temp harness copy
```

`omniagi check` must print `RESULT: PASS`, and must leave `git status` clean.
If it ever dirties the tree, that is a bug.

## Commands

| Command | Purpose |
|---|---|
| `omniagi check` | Run every named check: registry, constitution, links, hashes, memory, docs. |
| `omniagi route <task>` | Score the task, pick a specialist and an engine seat. `--explain` shows why. |
| `omniagi hash <path>` | SHA-256 a harness file. `--write-manifest` / `--verify-manifest` for the constitution manifest. |
| `omniagi docs` | Regenerate every table derived from the registry. `--check` fails when stale. |
| `omniagi extend <tool_id>` | Run the six-step self-extension protocol. `--demo` runs it in a throwaway copy. |
| `omniagi memory` | Audit durable memory for expiry and hygiene. |
| `omniagi watch --once` | One watchdog health check; without `--once` it loops with backoff. See [deploy/](deploy/README.md). |
| `omniagi seats` | List engine seats with provenance and availability. |
| `omniagi tool list` / `omniagi tool run <id>` | Execute a registered tool: schema-validated args, timeout, JSON result. |
| `omniagi loop <task>` | The closed loop: route → seat call → tool calls → verify → changelog. |
| `omniagi eval` | Replay the task fixture and score every task pass/fail. |

The legacy `scripts/*.py` entry points still work as thin wrappers.

## The closed loop

`omniagi loop "<task>"` runs one full pass and reports what actually happened:

1. **route** the task to a specialist and an engine seat (weighted scoring),
2. **call** that seat over an OpenAI-compatible endpoint,
3. **act** — every `{"tool": ..., "args": {...}}` the model emits is dispatched
   through the registry runtime: schema-validated, timed out, JSON result,
4. **verify** — a pass requires at least one tool call and zero failures; a
   non-zero exit or a failed read-back is never rendered as success,
5. **log** one changelog line recording the outcome, pass *or* fail.

The model contract is one JSON object per tool call, so a 7B local model can
satisfy it. With no seat reachable the loop exits `3` with a blocker instead of
inventing output.

Three tools are executable today — `file_read`, `file_write` (verified by
read-back) and `shell` (argv form, allowlisted, bounded). The rest of the
registry is marked `spec only` in `TOOLS.md` and is refused at dispatch: a tool
that cannot run says so.

## Does it work? Ten tasks say so

`omniagi eval` replays `tests/fixtures/loop_tasks.json` — ten tasks, each with a
recorded model reply, executed for real in a throwaway harness copy and scored
on behaviour: files written, exit codes, refusals. Six expect success, four
expect a specific refusal (non-allowlisted command, unregistered tool, invalid
arguments, a path escaping the harness root). It is not a check that the
markdown still has a "Verify" heading.

## Engine seats are quarantined

All ten seats ship `quarantined`: their ranking comes from a model catalogue,
and none has ever answered a request from this harness. Quarantined seats are
reported unavailable and refused by the adapter, so the harness reports a
blocker rather than routing work to an unproven engine. The *transport* is
proven — `tests/test_adapters.py` runs the full request/response cycle against a
stub OpenAI-compatible server on localhost, on by default. Promoting a seat
requires calling it for real and recording the evidence; `omniagi check` fails
if an active seat is backed by anything weaker
([ADR 0005](docs/adr/0005-seat-quarantine.md)).

## How it works

`registry/harness.json` is the single source of truth for tools, agents, engine
seats, routing rules and the non-negotiables. Every markdown table describing
that data is generated from it, and CI fails when a generated block is stale —
so the registry and the documentation cannot silently disagree.

See [docs/architecture.md](docs/architecture.md).

## Layout

```
registry/                  # harness.json (source of truth) + JSON Schema
omniagi/                   # the executable harness (zero runtime dependencies)
tests/                     # pytest: goldens, negative tests, round-trips
OmniAGI.md                 # master identity + ownership
WORLD_AGENTS.md            # constitution (NOT AGENTS.md - Hermes-protected name)
MEMORY.md + memory/        # durable world state, changelog, hash manifest
TOOLS.md + tools/          # tool registry + specs
workflows/                 # agent-loop, tool-extension, model-routing, memory-consolidation
harnesses/                 # Top-10 agentic MoE engine seats
agents/                    # specialist subroutines (owned by master)
docs/                      # architecture, threat model, ADRs, tutorial
deploy/                    # systemd and launchd units for the watchdog
scripts/                   # thin wrappers over the omniagi CLI
references/                # generated evidence mirrors
```

## Non-negotiables

Each is a named check function, so a CI failure names the rule that broke.

| Rule | Check |
|---|---|
| Never invent a second master. | `constitution.single_master` |
| Never simulate tool success — real read-back and exit codes only. | `constitution.no_simulated_success` |
| Missing tool → follow the tool-extension protocol. | `constitution.tool_extension_protocol` |
| Prefer the smallest patch that restores capability. | `constitution.smallest_patch` |
| Durable memory must stay current and machine-independent. | `memory.expiry_audit`, `memory.hygiene` |

## CI

Every push runs, across Python 3.10–3.13 on Ubuntu and macOS:

- the full test suite with coverage;
- `ruff`, `mypy`, and a dependency audit;
- `omniagi check` and `omniagi docs --check`;
- `omniagi eval` — the ten-task behavioural fixture;
- `omniagi tool run` against a real file, asserting the JSON result;
- an assertion that the hasher emits **64 hexadecimal characters** and exits
  non-zero on a missing file — the previous CI checked only the exit status, and
  the tool it "verified" printed an error and exited `0`;
- a guarantee that verification did not modify the working tree.

## Contributing

Start with [docs/tutorial-add-a-tool.md](docs/tutorial-add-a-tool.md), then read
[CONTRIBUTING.md](CONTRIBUTING.md). Constitutional changes require an
[ADR](docs/adr/README.md). Security posture is documented in
[docs/threat-model.md](docs/threat-model.md).

## Origin

Built from the recursive OmniAGI execution prompt in `ENHANCED_PROMPT.md`.
Machine-local paths and host state belong in `memory/local.md` (gitignored); see
the tracked template beside it.

GitHub: https://github.com/kaiclean/omniagi-world-model

## License

[MIT](LICENSE)
