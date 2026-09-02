"""Self-healing watchdog.

Improvements over the original:

* portable root (no hardcoded ``/Users/<name>`` path)
* ``--once`` mode so CI can exercise it
* exponential backoff between retries instead of a single shot
* a pluggable alert sink (stderr, file, or a command from the shell allowlist)
* silent on healthy runs, loud and specific on failure
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .paths import resolve
from .results import Status
from .selfcheck import Report, run_checks

LOG_FILE = "memory/watchdog.log"
DEFAULT_INTERVAL_SECONDS = 900.0
DEFAULT_MAX_BACKOFF_SECONDS = 3600.0


@dataclass
class WatchdogConfig:
    interval: float = DEFAULT_INTERVAL_SECONDS
    max_backoff: float = DEFAULT_MAX_BACKOFF_SECONDS
    strict: bool = False
    log_path: Path | None = None


def _log(message: str, config: WatchdogConfig) -> None:
    path = config.log_path or resolve(LOG_FILE)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError as exc:  # pragma: no cover - defensive
        print(f"watchdog: cannot write log: {exc}", file=sys.stderr)


def format_alert(report: Report) -> str:
    lines = ["[OmniAGI Watchdog] harness health check FAILED:"]
    for result in report.results:
        if result.status is Status.PASS:
            continue
        lines.append(f"  [{result.status.value}] {result.name}: {result.summary}")
        for detail in result.details[:5]:
            lines.append(f"      - {detail}")
    return "\n".join(lines)


def stderr_sink(message: str) -> None:
    print(message, file=sys.stderr)


def check_once(config: WatchdogConfig, sink: Callable[[str], None] = stderr_sink) -> int:
    """Run one health check. Returns a process exit code."""
    report = run_checks()
    unhealthy = bool(report.failed) or (config.strict and bool(report.warned))
    if unhealthy:
        alert = format_alert(report)
        _log("ALERT\n" + alert, config)
        sink(alert)
        return 1
    _log("health check PASSED cleanly; harness intact", config)
    return 0


def watch(
    config: WatchdogConfig,
    sink: Callable[[str], None] = stderr_sink,
    sleep: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
) -> int:
    """Loop with exponential backoff on repeated failure.

    ``iterations`` bounds the loop so the behaviour is testable without wall
    clock time.
    """
    delay = config.interval
    completed = 0
    last_status = 0
    while iterations is None or completed < iterations:
        last_status = check_once(config, sink=sink)
        if last_status == 0:
            delay = config.interval
        else:
            delay = min(delay * 2, config.max_backoff)
            _log(f"backing off for {delay:g}s after failure", config)
        completed += 1
        if iterations is not None and completed >= iterations:
            break
        sleep(delay)
    return last_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OmniAGI self-healing watchdog.")
    parser.add_argument("--once", action="store_true", help="run a single check and exit")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="seconds between checks when healthy",
    )
    parser.add_argument(
        "--max-backoff",
        type=float,
        default=DEFAULT_MAX_BACKOFF_SECONDS,
        help="maximum backoff between checks after repeated failure",
    )
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="emit the failing report as JSON")
    args = parser.parse_args(argv)

    config = WatchdogConfig(
        interval=args.interval, max_backoff=args.max_backoff, strict=args.strict
    )

    if args.json:
        report = run_checks()
        print(json.dumps(report.to_dict(), indent=2))
        return 1 if report.failed or (args.strict and report.warned) else 0

    if args.once:
        return check_once(config)
    return watch(config)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
