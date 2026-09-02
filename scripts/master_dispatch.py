#!/usr/bin/env python3
"""Deprecated wrapper: use `omniagi route <task>`.

Routing is now weighted scoring with confidence and an escalation ladder rather
than first-match substring scanning.
"""

from __future__ import annotations

import json
import sys

import _bootstrap  # noqa: F401  (sys.path bootstrap)

from omniagi.routing import route

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No task provided"}), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(route(" ".join(sys.argv[1:])).to_dict(), indent=2))
