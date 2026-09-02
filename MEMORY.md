# MEMORY.md — OmniAGI Durable World State

> This file is the long-term memory of OmniAGI. Unlike scratch logs, entries here must be:
> - **durable** (still true in a week)
> - **declarative** (facts, not instructions-to-self)
> - **compact** (high signal)
> Anti-staleness: entries that become stale MUST be corrected or removed here and noted in `memory/CHANGELOG.md`.

## Format
Each entry: a fact line. Optional `# tag` for category. No bullet spam.

## Seeded world facts (2026-09-02)
# identity
OmniAGI is the sole master of this world model harness; specialist seats are owned subroutines, never peer masters.
# harness
Harness root: ~/research/omniagi-world-model/ on macOS (kaileanhard). Constitution: WORLD_AGENTS.md. Master spec: OmniAGI.md.
# engines
Top-10 engine seats live in harnesses/TOP10_AGENTIC_MOE.md. Primary cloud reasoner: Qwen3.5-397B-A17B. Coding seat: Qwen3-Coder-480B-A35B. Local fallback: Qwen3.5-9B-HauhauCS-Aggressive (LM Studio / Ollama; currently DOWN).
# machine
Host is MacBook Air 16GB; disk free ~4.3GB as of 2026-09-02 — avoid large model downloads without explicit reclaim.
# tooling
Self-extension protocol: workflows/tool-extension.md. Tool registry: TOOLS.md. Agents must verify writes via read-back or exit code.
# hermes
Hermes profile: ascension. AGENTS.md is a protected filename in Hermes; world-model constitution lives in WORLD_AGENTS.md to stay editable by OmniAGI.

## Research summaries
# agentic_moe
Agentic MoE research (2025–2026) converges on three axes: (1) MoE as backbone for agentic LLMs (Kimi K2 1T/32B, Nemotron 3 Nano/Super with LatentMoE + NVFP4), optimizing throughput per active param; (2) MoE inside agentic RL — PA-MoE uses phase-aware routing to fix simplicity bias by preserving temporally consistent expert specialization; (3) agentic routing/orchestration (ACRouter, SWE-Router) where an LLM dynamically selects models/experts per step using trajectory context, with Bayes-optimal temporal escalation. Core insight: token/step-level static routing is suboptimal for agentic tasks; temporally-aware routing is strictly better. Efficiency (active params, inference throughput) is the primary economic driver for agentic workloads. Benchmarks now evaluate multi-turn execution with regret/cost metrics (CodeRouterBench, TwinRouterBench). No single paper yet unifies all three axes.

## Update rules
- Only OmniAGI writes here (or a memory_keeper subroutine acting on its behalf).
- Before writing, read current state to avoid duplicate/contradictory entries.
- When correcting a fact, also append a one-liner to `memory/CHANGELOG.md` (what changed, date).
- Do NOT store session progress logs / TODO state here — those go in scratch files if needed.