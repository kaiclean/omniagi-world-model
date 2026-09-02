#!/usr/bin/env python3
"""Deprecated wrapper: use `omniagi check`.

Kept so existing documentation and CI invocations keep working. Unlike the
original implementation this is read-only and never mutates the working tree.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (sys.path bootstrap)

from omniagi.selfcheck import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
