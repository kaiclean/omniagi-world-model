#!/usr/bin/env python3
"""Self-extension showcase: use `omniagi extend --demo`.

Runs the full missing-tool protocol inside a temporary copy of the harness, so
the demonstration is real (files are written and read back) without ever
dirtying the working tree.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (sys.path bootstrap)

from omniagi.extend import ExtensionError, demo

if __name__ == "__main__":
    try:
        report = demo()
    except ExtensionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"temporary harness: {report.root}")
    for step in report.steps:
        print(step)
    print(f"verified: {report.verified}")
    sys.exit(0 if report.verified else 1)
