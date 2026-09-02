# Changelog

Append-only log of harness changes. Use `omniagi memory --log "<message>"`,
which prefixes the date and skips an identical consecutive entry.

- 2026-09-02 tool_added: summarize_url (self-extension demo) verified=True
- 2026-09-02 changelog: collapsed 6 duplicate self-extension demo entries; the demo now runs in a temporary harness copy and no longer mutates tracked files
- 2026-09-02 harness: registry/harness.json became the single source of truth; TOOLS.md, references/ and the routing table are now generated
- 2026-09-02 integrity: added memory/manifest.json constitution hash drift detection
- 2026-09-02 constitution: replaced string-match single-master enforcement with a structural invariant plus negative tests
- 2026-09-02 routing: replaced first-match substring routing with weighted scoring, confidence and an escalation ladder
- 2026-09-02 memory: MEMORY.md entries became structured rows with expiry auditing; machine-specific state moved to gitignored memory/local.md
- 2026-09-02 tooling: added the omniagi CLI, run traces, hardened shell tool, seat health probe and reference seat adapter
- 2026-09-02 tests: 204 pytest cases covering routing goldens, constitution negatives, hashing failure modes, shell refusals, memory expiry, self-extension round-trip and CLI exit codes (91.8% coverage)
- 2026-09-02 ci: matrix (ubuntu+macos x py3.10-3.13), pinned action SHAs, contents:read permissions, ruff+mypy+pip-audit, hasher output asserted as 64 hex chars, clean-tree guarantee
- 2026-09-02 docs: architecture, threat model, ADR log (single master, registry as source of truth, fail loudly), add-a-tool tutorial; README rewritten around the omniagi CLI
- 2026-09-02 adapters: reference seat adapter now exercised end-to-end against a stub OpenAI-compatible server (17 tests, coverage omit removed); malformed and non-HTTP responses must raise, never coerce
- 2026-09-02 deploy: systemd service+timer and launchd plist for the watchdog, validated by tests that parse each unit with the real CLI parser
- 2026-09-02 cli: 'omniagi watch' gained --max-backoff and --json, found missing by the deploy-unit tests
