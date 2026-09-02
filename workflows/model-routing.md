# Workflow: Model Routing

> How OmniAGI picks an engine seat for a request.

## Default routing table

| Work class | Engine seat | Condition |
|------------|-------------|-----------|
| Hard reasoning / planning (long horizon) | Qwen3.5-397B-A17B (cloud) | API available |
| Coding / tool implementation / patches | Qwen3-Coder-480B-A35B (cloud) | API available |
| High-stakes verification / 2nd opinion | DeepSeek-R1 or Qwen3-235B-A22B-Thinking | API available |
| Routine strong work (cost/quality mid) | Qwen3.5-122B-A10B | API available |
| Fast scout / cheap loop | Qwen3.6-35B-A3B or Qwen3-Next-80B-A3B | API available |
| Local fallback (offline / private / cloud down) | Qwen3.5-9B-HauhauCS (LM Studio / Ollama) | Local up |
| Structured dashboard / ops | GLM-4.7-Flash / GLM-5 (API) | API available |

## Routing rules
1. Check if a cloud API seat is reachable (provider auth + network).
2. If no cloud seat reachable → local fallback (if up).
3. If neither → report a blocker; do NOT simulate model output.
4. Only OmniAGI may change this routing table (change must be written to this file + logged in changelog).
5. Specialist subroutines inherit the routing; they cannot permanently own a seat.

## How to call a seat
- Use Hermes provider/model config (`hermes config set model.provider <p> ; hermes config set model.default <m>`)
- Or call the provider API directly from a `scripts/` tool when documented.
- Always pass a system prompt that identifies as OmniAGI operating under `OmniAGI.md`.