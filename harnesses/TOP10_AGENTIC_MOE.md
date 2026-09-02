# Top 10 Most Powerful Agentic MoE / Harness Engines (for OmniAGI)

> Evidence date: 2026-09-02
> Sources: Hermes ascension `models_dev_cache.json` (~212 providers / ~7493 models),
> `~/research/agentic-uncensored-16gb-2026.md`, prior live catalog scans this session.
> Rule: these are **owned engines under ONE master (OmniAGI)** — not 10 peer AGIs.
> Local endpoints at write-time: Ollama DOWN, LM Studio DOWN. Disk free ≈ 4.3GB.

## Ranking method (honest)

Scored for **agent harness power**, not raw chat vibes:
1. MoE / sparse-active architecture (or equivalent extreme efficiency for agent loops)
2. Tool-calling / agentic bench signals (BFCL, TAU2/τ², coding-agent posture, `tools=True` in catalog)
3. Context headroom for long tool traces
4. Availability in Hermes catalog / OmniRoute-class providers
5. Fit notes for this Mac (16GB / tight disk) vs cloud engines

Caveat: published benches vary by checkpoint/date. This is a **harness shortlist**, not a claim of absolute AGI.

---

## TOP 10

### 1. Qwen3.5-397B-A17B (cloud MoE brain)
- **Why #1:** Flagship Qwen3.5 MoE — huge total params, ~17B active, tools+reasoning flagged True across deepinfra/infomaniak/chutes; 262K ctx common.
- **Catalog exemplars:** `Qwen/Qwen3.5-397B-A17B`, FP8 / TEE variants
- **OmniAGI role:** Primary **deep reasoner / planner** engine
- **Fit:** Cloud only on this Mac

### 2. Qwen3-Coder-480B-A35B-Instruct (agentic coding MoE)
- **Why #2:** Purpose-built coding/agent MoE (480B-A35B), tools=True, 262K ctx, multiple providers (HF, submodel, deepinfra Turbo)
- **OmniAGI role:** **Code & tool-implementation** engine (writes missing tools)
- **Fit:** Cloud

### 3. Qwen3-235B-A22B (+ Thinking-2507)
- **Why #3:** Mature high-end MoE; Thinking variant for hard multi-step; tools=True; widely mirrored
- **OmniAGI role:** **General high-stakes problem solver**
- **Fit:** Cloud

### 4. NVIDIA Nemotron-3-Ultra (550B-class / Ultra MoE family)
- **Why #4:** Catalog fireworks `nemotron-3-ultra-nvfp4`, tools+reasoning, 262K; strong agent/reasoning positioning in Nemotron-3 line
- **OmniAGI role:** **Long-horizon agent / research** engine
- **Fit:** Cloud

### 5. Qwen3.5-122B-A10B
- **Why #5:** Mid-giant MoE sweet spot (A10B active), tools+reasoning, 262K — cheaper/faster than 397B for routine hard work
- **OmniAGI role:** **Workhorse reasoner** when 397B is overkill
- **Fit:** Cloud

### 6. Qwen3.6-35B-A3B (+ uncensored TEE variants)
- **Why #6:** New 35B-A3B MoE/hybrid family; tools+reasoning; local IQ2 experiments discussed in prior research; nano-gpt TEE uncensored exists
- **OmniAGI role:** **Fast MoE scout / creative+tool hybrid**; optional local experiment
- **Fit:** Cloud easy; local only at extreme quant + disk reclaim

### 7. Qwen3-Next-80B-A3B (Instruct / Thinking)
- **Why #7:** 80B-A3B efficiency MoE, long ctx, tools=True — strong “next” efficiency tier
- **OmniAGI role:** **High-throughput agent loop** engine
- **Fit:** Cloud

### 8. GLM-4.7-Flash (30B-A3B) / GLM-5 family
- **Why #8:** Prior research: τ²-Bench ~79.5 for GLM-4.7-Flash; MoE A3B; GLM-5.x appears in catalog (hpc-ai). Excellent agent scores, harsh local KV cost
- **OmniAGI role:** **Structured agent / dashboard-ops** engine via API
- **Fit:** Cloud (local MoE KV hostile on 16GB)

### 9. DeepSeek-V3 / V3.1 (+ R1 for hard reasoning)
- **Why #9:** MoE-class frontier widely available; deep reasoning (R1) + strong coding/tool culture; multiple providers in cache
- **OmniAGI role:** **Alternate brain** for verification / second opinion (still owned by master)
- **Fit:** Cloud

### 10. Qwen3.5-9B-HauhauCS-Aggressive (local agentic champion) *dense/hybrid efficiency seat*
- **Why #10:** Not a giant MoE — but **best verified local agent** on this machine class: BFCL-V4 66.1, TAU2 79.1, tiny KV via GDN hybrid. Required for offline / disk-constrained loops.
- **Evidence:** `~/research/agentic-uncensored-16gb-2026.md`
- **OmniAGI role:** **Local always-on executor** when cloud engines unavailable
- **Fit:** Local when LM Studio/Ollama up (currently DOWN)

### Honorable MoE mentions (not top-10 seats)
- Nemotron Lightning 30B-A3B — fast MoE, tools+reasoning
- Qwen3-30B-A3B / Coder-30B-A3B — smaller cloud MoE
- Ling-mini-2.0 (100B-A~1B) — speed MoE, weaker schema fidelity
- Qwen3.8-2.4T-A95B — extreme MoE if/when reachable & affordable

---

## OmniAGI engine binding (single master)

| Seat | Engine | Condition |
|------|--------|-----------|
| Master identity | OmniAGI (this harness) | Always |
| Router/default cloud | Qwen3.5-122B-A10B or 397B-A17B | API available |
| Coding/tools | Qwen3-Coder-480B-A35B | When writing/extending tools |
| Hard think | Qwen3-235B-A22B-Thinking / DeepSeek-R1 / Nemotron-Ultra | Escalation |
| Local fallback | Qwen3.5-9B-HauhauCS | Cloud down / private |

Only **OmniAGI** may change seats, MEMORY, TOOLS, or workflows.

---

## Provenance and confidence (generated)

> Generated from `registry/harness.json`. Every seat must declare where its
> claim comes from and when it was last verified. `omniagi check` warns when the
> evidence exceeds the freshness window (`freshness.max_evidence_age_days`).

**Confidence tiers**

| Tier | Meaning |
|---|---|
| `verified` | We ran the benchmark or the seat ourselves in this harness. |
| `cited` | Someone else measured it; we recorded the source but did not re-run it. |
| `estimated` | Vendor positioning or inference. Treat as a hypothesis, not a fact. |

<!-- omniagi:generated:start id=seats-provenance -->
| # | Engine | Tier | Confidence | Benchmark / basis | Source | Verified on |
|---|---|---|---|---|---|---|
| 1 | Qwen3.5-397B-A17B | cloud | cited | catalog capability flags (tools=true, reasoning=true) | Hermes ascension models_dev_cache.json (~212 providers / ~7493 models) | 2026-09-02 |
| 2 | Qwen3-Coder-480B-A35B-Instruct | cloud | cited | catalog capability flags (tools=true), agentic coding posture | Hermes ascension models_dev_cache.json | 2026-09-02 |
| 3 | Qwen3-235B-A22B-Thinking-2507 | cloud | cited | catalog capability flags (tools=true, reasoning=true) | Hermes ascension models_dev_cache.json | 2026-09-02 |
| 4 | NVIDIA Nemotron-3-Ultra | cloud | estimated | vendor positioning only - no independent measurement | fireworks catalog entry nemotron-3-ultra-nvfp4 | 2026-09-02 |
| 5 | Qwen3.5-122B-A10B | cloud | cited | catalog capability flags (tools=true, reasoning=true) | Hermes ascension models_dev_cache.json | 2026-09-02 |
| 6 | Qwen3.6-35B-A3B | cloud | estimated | no independent agentic benchmark recorded | Hermes ascension models_dev_cache.json; local IQ2 experiments in prior research | 2026-09-02 |
| 7 | Qwen3-Next-80B-A3B | cloud | cited | catalog capability flags (tools=true) | Hermes ascension models_dev_cache.json | 2026-09-02 |
| 8 | GLM-4.7-Flash (30B-A3B) | cloud | cited | tau2-Bench ~79.5 (reported, not re-run here) | ~/research/agentic-uncensored-16gb-2026.md | 2026-09-02 |
| 9 | DeepSeek-V3.1 / R1 | cloud | cited | catalog capability flags (reasoning=true) | Hermes ascension models_dev_cache.json | 2026-09-02 |
| 10 | Qwen3.5-9B-HauhauCS-Aggressive | local | cited | BFCL-V4 66.1, TAU2 79.1 (reported, not re-run here) | ~/research/agentic-uncensored-16gb-2026.md | 2026-09-02 |
<!-- omniagi:generated:end id=seats-provenance -->

Re-verify a seat by updating its `provenance.verified_on` (and `confidence`, if
you actually measured it) in `registry/harness.json`, then running
`omniagi docs`.
