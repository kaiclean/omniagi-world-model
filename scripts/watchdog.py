#!/usr/bin/env python3
"""Deprecated wrapper: use `omniagi watch [--once]`."""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401  (sys.path bootstrap)

from omniagi.watchdog import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
