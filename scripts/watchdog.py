#!/usr/bin/env python3
"""
OmniAGI Local Self-Healing Watchdog
Runs periodically to audit harness integrity, verify tool registrations,
test active tools, and enforce the single-master constitution.

Silent on healthy runs (classic watchdog pattern).
Emits alerts only on failure or corruption.
"""
from __future__ import annotations
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HARNESS_ROOT = Path("/Users/kaileanhard/research/omniagi-world-model")
SELFCHECK = HARNESS_ROOT / "scripts" / "selfcheck.py"
HASHER = HARNESS_ROOT / "scripts" / "hasher.py"
CHANGELOG = HARNESS_ROOT / "memory" / "CHANGELOG.md"
WATCHDOG_LOG = HARNESS_ROOT / "memory" / "watchdog.log"

def log(msg: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
    with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
        f.write(line)

def run_cmd(cmd: list[str]) -> tuple[int, str]:
    res = subprocess.run(
        cmd,
        cwd=str(HARNESS_ROOT),
        capture_output=True,
        text=True
    )
    return res.returncode, (res.stdout + "\n" + res.stderr).strip()

def main() -> int:
    errors = []

    # 1. Run full harness selfcheck (enforces single master, self-extension loop, registries)
    rc, out = run_cmd([sys.executable, str(SELFCHECK)])
    if rc != 0 or "RESULT: PASS" not in out:
        errors.append(f"selfcheck.py FAILED (exit {rc}):\n{out[-400:]}")

    # 2. Test live tool execution (file_hasher)
    rc, out = run_cmd([sys.executable, str(HASHER), "OmniAGI.md"])
    if rc != 0 or len(out.strip()) != 64:
        errors.append(f"hasher.py tool execution failed (exit {rc}): {out}")

    # 3. Check for unauthorized extra masters or constitution drift
    world_agents = (HARNESS_ROOT / "WORLD_AGENTS.md").read_text(encoding="utf-8")
    if "Count:** exactly 1" not in world_agents and "Count: exactly 1" not in world_agents:
        errors.append("Constitution drift: 'Count: exactly 1' master rule missing or corrupted!")

    if errors:
        alert = f"🚨 [OmniAGI Watchdog Alert] Harness health check failed:\n" + "\n---\n".join(errors)
        log(f"ALERT:\n{alert}")
        print(alert)
        return 1

    # Healthy: log quietly, no stdout noise
    log("Health check PASSED cleanly. Harness intact.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
