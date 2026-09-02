"""Make the harness package importable when running scripts from a checkout.

The scripts in this directory are thin backwards-compatible wrappers around the
``omniagi`` package. They work whether or not the package has been installed
with ``pip install -e .``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
