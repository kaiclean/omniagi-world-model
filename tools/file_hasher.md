# Tool: file_hasher
Added by OmniAGI self-extension on 2026-09-02.

## Purpose
Compute SHA-256 hash of a harness file for integrity verification.

## Inputs
- file_path (str): relative path from root (e.g., 'OmniAGI.md')

## Outputs
- hash (str): 64-char hex string
- verified (bool)

## How to invoke
- Shell: `sha256sum <file_path> | cut -d' ' -f1`

## Dependencies
- coreutils (sha256sum) or Python

## Verification
- Dry-run: Hash 'OmniAGI.md' and compare to a manual sha256sum run.
