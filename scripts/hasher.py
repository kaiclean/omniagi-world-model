#!/usr/bin/env python3
"""Deprecated wrapper: use `omniagi hash <path>`.

Exits non-zero when the file is missing instead of printing an error string
with a success status.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (sys.path bootstrap)

from omniagi.hashing import HashError, hash_file

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: hasher.py <harness-relative-path>", file=sys.stderr)
        sys.exit(2)
    try:
        print(hash_file(sys.argv[1]))
    except HashError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
