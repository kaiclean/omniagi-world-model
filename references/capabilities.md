# Capabilities & Providers (generated)

> Capability risk/approval matrix and model providers, generated from
> `registry/harness.json`. Do not edit by hand; run `omniagi docs` to refresh.

Tools declare the capabilities they exercise. Each capability carries a risk
level and an approval level drawn from the registry `policies` section: `auto`
capabilities may be used without asking, `master` capabilities require the
single master, and `human` capabilities need an out-of-band human approval.
High-risk capabilities are never left on `auto`.

## Capabilities

<!-- omniagi:generated:start id=capabilities-table -->
| Capability | Risk | Approval | Description |
|---|---|---|---|
| `fs_read` | low | auto | Read files inside the harness root. |
| `fs_write` | high | master | Create or modify files inside the harness root. |
| `process_exec` | high | master | Execute allowlisted subprocesses via the hardened shell. |
| `network` | high | master | Make outbound network requests to model or web endpoints. |
| `registry_write` | high | master | Modify the canonical registry that governs the harness. |
| `memory_write` | medium | auto | Append to or rewrite the audited memory and changelog files. |
<!-- omniagi:generated:end id=capabilities-table -->

## Providers

Model providers describe how engine seats reach an inference endpoint and which
credential variables unlock them.

<!-- omniagi:generated:start id=providers-table -->
| Provider | Tier | Health probe | Default base URL | Credential variables |
|---|---|---|---|---|
| `gateway` | cloud | credential | — | `OMNIAGI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPINFRA_API_KEY`, `TOGETHER_API_KEY` |
| `local` | local | endpoint | http://127.0.0.1:11434/v1 | — |
<!-- omniagi:generated:end id=providers-table -->
