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
