# OmniAGI World Model Harness

A single-master, self-extending agent world model — where every claim about the
system is checked by code rather than asserted in prose.

> Exactly **one** master: **OmniAGI**. Top-10 MoE/agentic engines are owned
> seats, not peer AGIs. That is not a slogan; it is
> [an enforced structural invariant](docs/adr/0001-single-master-authority.md)
> with tests that prove the check fails when a second master is injected.

## Quick start

```bash
python3 -m pip install -e ".[dev]"

omniagi check                        # verify the harness (read-only, idempotent)
omniagi route "fix the failing test" --explain
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
| `omniagi watch --once` | One watchdog health check; without `--once` it loops with backoff. |
| `omniagi seats` | List engine seats with provenance and availability. |

The legacy `scripts/*.py` entry points still work as thin wrappers.

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
