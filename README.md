# OmniAGI World Model Harness

Single-master, self-extending, self-healing agent world model.

> Exactly **one** master: **OmniAGI**. Top-10 MoE/agentic engines are owned seats, not peer AGIs.

## Quick start

```bash
# Integrity + self-extension demo (must print RESULT: PASS)
python3 scripts/selfcheck.py

# Route a task to specialist + engine seat
python3 scripts/master_dispatch.py "implement a missing file hasher tool"

# Extend a tool yourself (real protocol)
python3 scripts/extend_tool.py file_hash "SHA256 a local file" --impl
```

## Layout

```
OmniAGI.md                 # master identity + ownership
WORLD_AGENTS.md            # constitution (NOT AGENTS.md — Hermes-protected name)
MEMORY.md + memory/        # durable world state + changelog
TOOLS.md + tools/          # tool registry + specs
workflows/                 # agent-loop, tool-extension, model-routing, memory-consolidation
harnesses/                 # Top-10 agentic MoE engine seats
agents/                    # specialist subroutines (owned by master)
scripts/                   # selfcheck, dispatch, extend_tool
references/                # condensed evidence mirrors
```

## Non-negotiables

1. Never invent a second master.
2. Never simulate tool success — real read-back / exit codes only.
3. Missing tool → follow `workflows/tool-extension.md`.
4. Prefer the smallest patch that restores capability.

## CI

GitHub Actions runs `scripts/selfcheck.py` on every push to `main`.

## Origin

Built from the recursive OmniAGI execution prompt in `ENHANCED_PROMPT.md`.
Local research root: `~/research/omniagi-world-model/`.
GitHub: https://github.com/kaiclean/omniagi-world-model (private).
