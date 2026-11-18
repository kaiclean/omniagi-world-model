# Security policy

## Supported version

Only the latest state of `main` is supported. The package version is declared in
`pyproject.toml`.

## Reporting a problem

Please report vulnerabilities privately through GitHub private vulnerability
reporting on this repository (Security tab, "Report a vulnerability"). If that is
not available, open an issue that says only that you have a security report and
the maintainer will arrange a private channel. Do not post exploit details in a
public issue.

## Threat model in short

The full analysis is in [docs/explanation/threat-model.md](docs/explanation/threat-model.md). In brief:

- Shell execution takes an argument vector, never `shell=True`, only
  allowlisted executables, with a timeout (`omniagi/shell.py`).
- File hashing and working directories are resolved and rejected when they fall
  outside the harness root (`omniagi/hashing.py`, `omniagi/shell.py`).
- Constitution files are pinned by SHA-256 in `memory/manifest.json`;
  `omniagi check` reports drift.
- Credentials are read from environment variables only; engine seats raise
  `SeatUnavailable` instead of returning placeholder output
  (`omniagi/adapters.py`).
- The harness has zero runtime dependencies; CI pins actions to commit SHAs and
  runs `pip-audit` (`.github/workflows/ci.yml`).

## Out of scope

- Sandboxing an agent from the host: the allowlist reduces the cost of mistakes
  and is not a security boundary against an adversary with repository write
  access.
- Compromised CI runners or malicious maintainers.
- Security of third-party model providers reached through the optional adapter.
