# Tool: file_hasher

Compute the SHA-256 hash of a harness file for integrity verification.

## Purpose
Back the constitution hash manifest (`memory/manifest.json`) so tampering or
accidental drift in a constitution file is detected rather than assumed away.

## Inputs
- file_path (str): harness-relative path, e.g. `OmniAGI.md`. Paths that escape
  the harness root are rejected.

## Outputs
- hash (str): 64-character lowercase hex digest.

## How to invoke
- CLI: `omniagi hash OmniAGI.md`
- Manifest: `omniagi hash --write-manifest` / `omniagi hash --verify-manifest`
- Python: `from omniagi.hashing import hash_file`

## Dependencies
- none (Python standard library `hashlib`)

## Failure behaviour
Raises `HashError` and exits non-zero when the file is missing. It never returns
a sentinel string: the original implementation printed `Error: File not found`
and exited 0, so CI reported success for a completely broken tool.

## Verification
- `omniagi hash OmniAGI.md` must print 64 hex characters and exit 0.
- `omniagi hash no-such-file` must print to stderr and exit 1.
- Compare against `sha256sum OmniAGI.md`.
