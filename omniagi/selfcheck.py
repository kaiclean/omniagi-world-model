"""Read-only harness verification.

``selfcheck`` runs every named check and reports the result. It is **idempotent
and non-mutating**: running it never writes to the working tree, so CI can run
it on every push without producing a dirty diff (the previous implementation
rewrote ``TOOLS.md`` and appended to the changelog on every invocation).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import constitution, docgen, health, integrity, memory
from .hashing import check_manifest
from .registry import Registry, RegistryError, load_registry
from .results import CheckResult, Status


@dataclass
class Report:
    results: list[CheckResult]

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.status is Status.FAIL]

    @property
    def warned(self) -> list[CheckResult]:
        return [r for r in self.results if r.status is Status.WARN]

    @property
    def ok(self) -> bool:
        return not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": "PASS" if self.ok else "FAIL",
            "counts": {
                "pass": sum(1 for r in self.results if r.status is Status.PASS),
                "warn": len(self.warned),
                "fail": len(self.failed),
            },
            "checks": [r.to_dict() for r in self.results],
        }


def run_checks(registry: Registry | None = None, probe_network: bool = False) -> Report:
    """Run every check. Never mutates the harness."""
    try:
        reg = registry or load_registry()
    except RegistryError as exc:
        return Report([CheckResult.failed("registry.load", str(exc))])

    results: list[CheckResult] = [
        CheckResult.passed(
            "registry.load",
            f"registry v{reg.data['version']} loaded: "
            f"{len(reg.tools)} tools, {len(reg.agents)} agents, {len(reg.seats)} seats",
        )
    ]
    results.extend(integrity.all_checks(reg))
    results.append(docgen.check_docs(reg))
    results.append(check_manifest(reg))
    results.extend(constitution.all_checks(reg))
    results.extend(memory.all_checks())
    results.append(_check_seat_freshness(reg))
    results.append(health.check_health_probe(reg) if not probe_network else _probe(reg))
    return Report(results)


def _probe(reg: Registry) -> CheckResult:
    results = health.probe_all(reg, probe_network=True)
    available = [h.seat_id for h in results if h.available]
    if not available:
        return CheckResult.warned(
            "routing.health_probe",
            "no engine seat reachable after a live probe - model calls must report a blocker",
            [h.reason for h in results],
        )
    return CheckResult.passed(
        "routing.health_probe", f"{len(available)}/{len(results)} seats reachable: {', '.join(available)}"
    )


def _check_seat_freshness(reg: Registry) -> CheckResult:
    """Warn when engine-seat evidence is older than the configured window."""
    from datetime import date, datetime

    name = "evidence.seat_freshness"
    limit = reg.max_evidence_age_days
    today = date.today()
    stale: list[str] = []
    errors: list[str] = []
    for seat in reg.seats:
        raw = seat["provenance"]["verified_on"]
        try:
            verified = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"seat '{seat['id']}' has an unparseable verified_on {raw!r}")
            continue
        age = (today - verified).days
        if age > limit:
            stale.append(f"{seat['id']}: evidence is {age} days old (limit {limit})")
    if errors:
        return CheckResult.failed(name, "seat provenance is malformed", errors)
    if stale:
        return CheckResult.warned(name, "engine-seat evidence is stale - re-verify the ranking", stale)
    return CheckResult.passed(name, f"all {len(reg.seats)} seats have evidence newer than {limit} days")


def format_report(report: Report, verbose: bool = False) -> str:
    lines = ["OmniAGI harness verification", "=" * 60]
    for result in report.results:
        lines.append(f"[{result.status.value:<4}] {result.name:<38} {result.summary}")
        if result.details and (verbose or result.status is not Status.PASS):
            for detail in result.details:
                lines.append(f"         - {detail}")
    lines.append("=" * 60)
    counts = report.to_dict()["counts"]
    lines.append(
        f"pass={counts['pass']} warn={counts['warn']} fail={counts['fail']}"
    )
    lines.append(f"RESULT: {'PASS' if report.ok else 'FAIL'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``scripts/selfcheck.py`` and the CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify the OmniAGI harness (read-only).")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="show details for passing checks")
    parser.add_argument(
        "--probe-network",
        action="store_true",
        help="probe engine seats over the network (off by default so CI stays offline)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures",
    )
    args = parser.parse_args(argv)

    report = run_checks(probe_network=args.probe_network)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report, verbose=args.verbose))
    if not report.ok:
        return 1
    if args.strict and report.warned:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
