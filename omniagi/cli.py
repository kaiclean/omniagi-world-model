"""Single CLI entry point: ``omniagi <command>``.

Replaces the four ad-hoc scripts. The old ``scripts/*.py`` entry points remain
as thin wrappers so existing muscle memory and documentation keep working.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .watchdog import DEFAULT_INTERVAL_SECONDS, DEFAULT_MAX_BACKOFF_SECONDS


def _cmd_check(args: argparse.Namespace) -> int:
    from .selfcheck import main as selfcheck_main

    argv: list[str] = []
    if args.json:
        argv.append("--json")
    if args.verbose:
        argv.append("--verbose")
    if args.probe_network:
        argv.append("--probe-network")
    if args.strict:
        argv.append("--strict")
    return selfcheck_main(argv)


def _cmd_route(args: argparse.Namespace) -> int:
    from .routing import RoutingContext, escalate, explain, route

    task = " ".join(args.task).strip()
    if not task:
        print("error: no task provided", file=sys.stderr)
        return 2

    context = RoutingContext(task=task, attempt=args.attempt)
    decision = route(task, context=context, top_n=args.top)
    for reason in args.failed or []:
        decision = escalate(decision, reason)

    if args.explain:
        print(explain(decision))
    else:
        print(json.dumps(decision.to_dict(), indent=2))
    return 0


def _cmd_hash(args: argparse.Namespace) -> int:
    from .hashing import HashError, check_manifest, hash_file, write_manifest

    if args.write_manifest:
        path = write_manifest()
        print(f"wrote {path}")
        return 0
    if args.verify_manifest:
        result = check_manifest()
        print(f"[{result.status.value}] {result.name}: {result.summary}")
        for detail in result.details:
            print(f"  - {detail}")
        return 0 if result.ok else 1
    if not args.path:
        print("error: provide a path, --write-manifest or --verify-manifest", file=sys.stderr)
        return 2
    try:
        print(hash_file(args.path))
    except HashError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_docs(args: argparse.Namespace) -> int:
    from .docgen import DocgenError, generate

    try:
        changed = generate(check_only=args.check)
    except DocgenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        if changed:
            print("stale generated documentation:")
            for path in changed:
                print(f"  - {path}")
            print("run 'omniagi docs' to regenerate")
            return 1
        print("generated documentation is up to date")
        return 0
    if changed:
        for path in changed:
            print(f"regenerated {path}")
    else:
        print("no changes")
    return 0


def _cmd_extend(args: argparse.Namespace) -> int:
    from .extend import ExtensionError, demo, extend_tool

    try:
        report = (
            demo()
            if args.demo
            else extend_tool(
                tool_id=args.tool_id,
                name=args.name or args.tool_id.replace("_", " ").title(),
                purpose=args.purpose,
                script=args.script,
            )
        )
    except ExtensionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for step in report.steps:
        print(step)
    print(f"verified: {report.verified}")
    return 0 if report.verified else 1


def _cmd_memory(args: argparse.Namespace) -> int:
    from .memory import all_checks, append_changelog, dedupe_changelog, parse_memory

    if args.dedupe:
        removed = dedupe_changelog()
        print(f"removed {removed} duplicate changelog line(s)")
        return 0
    if args.log:
        written = append_changelog(args.log)
        print("appended" if written else "skipped duplicate entry")
        return 0
    if args.list:
        entries = [entry.to_dict() for entry in parse_memory()]
        print(json.dumps(entries, indent=2))
        return 0

    failed = False
    for result in all_checks():
        print(f"[{result.status.value}] {result.name}: {result.summary}")
        for detail in result.details:
            print(f"  - {detail}")
        failed = failed or not result.ok
    return 1 if failed else 0


def _cmd_world(args: argparse.Namespace) -> int:
    from .worldstate import WorldStateError, assert_fact, check_world_state, facts, get_fact

    if args.assert_key is not None:
        try:
            value = _coerce_world_value(args.value, args.type)
            resolution = assert_fact(
                key=args.assert_key,
                value=value,
                value_type=args.type,
                source=args.source,
                confidence=args.confidence,
            )
        except WorldStateError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(resolution.__dict__, indent=2))
        return 0
    if args.get is not None:
        fact = get_fact(args.get)
        if fact is None:
            print(f"error: no world-state fact named '{args.get}'", file=sys.stderr)
            return 1
        print(json.dumps(fact.to_dict(), indent=2))
        return 0
    if args.list:
        print(json.dumps([fact.to_dict() for fact in facts()], indent=2))
        return 0

    result = check_world_state()
    print(f"[{result.status.value}] {result.name}: {result.summary}")
    for detail in result.details:
        print(f"  - {detail}")
    return 0 if result.ok else 1


def _coerce_world_value(raw: str | None, value_type: str) -> Any:
    from .worldstate import WorldStateError

    if value_type == "null":
        return None
    if raw is None:
        raise WorldStateError(f"--value is required for type '{value_type}'")
    if value_type == "string":
        return raw
    if value_type == "boolean":
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        raise WorldStateError(f"invalid boolean {raw!r}")
    if value_type == "integer":
        try:
            return int(raw)
        except ValueError as exc:
            raise WorldStateError(f"invalid integer {raw!r}") from exc
    if value_type == "number":
        try:
            return float(raw)
        except ValueError as exc:
            raise WorldStateError(f"invalid number {raw!r}") from exc
    # object / array
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorldStateError(f"invalid JSON for {value_type}: {exc}") from exc


def _cmd_run(args: argparse.Namespace) -> int:
    from pathlib import Path

    from .orchestrator import Orchestrator, OrchestratorError, load_plan

    try:
        trace = getattr(args, "trace", None)
        if args.resume:
            orch = Orchestrator.resume(args.run_id, trace=trace)
        else:
            if not args.plan:
                print("error: provide a plan path (or --resume --run-id ID)", file=sys.stderr)
                return 2
            plan = load_plan(Path(args.plan))
            budget = _budget_overrides(args)
            orch = Orchestrator.from_plan(
                plan, run_id=args.run_id, budget=budget, trace=trace
            )
        state = orch.run()
    except OrchestratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(state.to_dict(), indent=2))
    else:
        print(f"run {state.run_id}: {state.status}")
        for task in state.tasks:
            print(f"  [{task.state:>7}] {task.id} ({task.kind}) - {len(task.attempts)} attempt(s)")
        for blocker in state.blockers:
            print(f"  blocker: {blocker}")
        print(
            f"spent: steps={state.spent_steps} "
            f"cost={state.spent_cost:g} seconds={state.spent_seconds:g}"
        )
        print(f"checkpoint: {orch.checkpoint_path}")
    return 0 if state.status == "completed" else 1


def _budget_overrides(args: argparse.Namespace) -> Any:
    from .orchestrator import Budget
    from .registry import load_registry

    budget = Budget.from_registry(load_registry())
    if args.max_steps is not None:
        budget.max_steps = args.max_steps
    if args.max_seconds is not None:
        budget.max_seconds = args.max_seconds
    if args.max_retries is not None:
        budget.max_retries = args.max_retries
    if args.max_cost is not None:
        budget.max_cost = args.max_cost
    return budget


def _cmd_watch(args: argparse.Namespace) -> int:
    from .watchdog import main as watchdog_main

    argv: list[str] = []
    if args.once:
        argv.append("--once")
    if args.strict:
        argv.append("--strict")
    if args.json:
        argv.append("--json")
    argv += ["--interval", str(args.interval), "--max-backoff", str(args.max_backoff)]
    return watchdog_main(argv)


def _cmd_seats(args: argparse.Namespace) -> int:
    from .health import probe_all

    results = [h.to_dict() for h in probe_all(probe_network=args.probe_network)]
    print(json.dumps(results, indent=2))
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import trace

    audits = [trace.audit_trace(Path(args.path))] if args.path else trace.audit_all()
    if args.json:
        print(json.dumps([a.to_dict() for a in audits], indent=2))
    elif not audits:
        print("no run traces recorded yet - nothing to audit")
    else:
        for audit in audits:
            status = "OK  " if audit.ok else "FAIL"
            print(f"[{status}] {audit.path} ({audit.events} events)")
            for error in audit.errors:
                print(f"         - {error}")
    return 0 if all(a.ok for a in audits) else 1


def _cmd_bench(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import bench

    try:
        suites = (
            [bench.run_file(Path(args.suite))] if args.suite else bench.run_all()
        )
    except bench.BenchError as exc:
        print(f"benchmark error: {exc}")
        return 2
    if args.json:
        print(json.dumps([s.to_dict() for s in suites], indent=2))
    else:
        print(bench.format_report(suites, verbose=args.verbose))
    return 0 if all(s.ok for s in suites) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omniagi", description="OmniAGI world-model harness.")
    parser.add_argument("--version", action="version", version=f"omniagi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="verify the harness (read-only)")
    check.add_argument("--json", action="store_true")
    check.add_argument("--verbose", "-v", action="store_true")
    check.add_argument("--probe-network", action="store_true")
    check.add_argument("--strict", action="store_true", help="treat warnings as failures")
    check.set_defaults(func=_cmd_check)

    route = sub.add_parser("route", help="route a task to a specialist and engine seat")
    route.add_argument("task", nargs="+")
    route.add_argument("--explain", action="store_true", help="human-readable reasoning")
    route.add_argument("--top", type=int, default=3, help="number of candidates to return")
    route.add_argument("--attempt", type=int, default=1, help="attempt number for escalation")
    route.add_argument(
        "--failed",
        action="append",
        metavar="REASON",
        help="record a prior failure and escalate (repeatable)",
    )
    route.set_defaults(func=_cmd_route)

    hasher = sub.add_parser("hash", help="hash a harness file or manage the manifest")
    hasher.add_argument("path", nargs="?")
    hasher.add_argument("--write-manifest", action="store_true")
    hasher.add_argument("--verify-manifest", action="store_true")
    hasher.set_defaults(func=_cmd_hash)

    docs = sub.add_parser("docs", help="regenerate registry-derived markdown")
    docs.add_argument("--check", action="store_true", help="fail if generated docs are stale")
    docs.set_defaults(func=_cmd_docs)

    extend = sub.add_parser("extend", help="run the self-extension protocol")
    extend.add_argument("tool_id", nargs="?", help="new tool id (lowercase_with_underscores)")
    extend.add_argument("--purpose", default="(describe the purpose)")
    extend.add_argument("--name", help="human-readable tool name")
    extend.add_argument("--script", help="harness-relative script implementing the tool")
    extend.add_argument(
        "--demo",
        action="store_true",
        help="run the protocol in a temporary harness copy (never touches this tree)",
    )
    extend.set_defaults(func=_cmd_extend)

    mem = sub.add_parser("memory", help="audit durable memory and the changelog")
    mem.add_argument("--list", action="store_true", help="print structured entries as JSON")
    mem.add_argument("--dedupe", action="store_true", help="collapse duplicate changelog lines")
    mem.add_argument("--log", metavar="MESSAGE", help="append a deduplicated changelog entry")
    mem.set_defaults(func=_cmd_memory)

    watch = sub.add_parser("watch", help="run the self-healing watchdog")
    watch.add_argument("--once", action="store_true", help="run a single check and exit")
    watch.add_argument("--strict", action="store_true", help="treat warnings as failures")
    watch.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="seconds between checks when healthy",
    )
    watch.add_argument(
        "--max-backoff",
        type=float,
        default=DEFAULT_MAX_BACKOFF_SECONDS,
        help="maximum delay between checks after repeated failure",
    )
    watch.add_argument("--json", action="store_true", help="emit the report as JSON")
    watch.set_defaults(func=_cmd_watch)

    seats = sub.add_parser("seats", help="probe engine-seat availability")
    seats.add_argument("--probe-network", action="store_true")
    seats.set_defaults(func=_cmd_seats)

    audit = sub.add_parser("audit", help="verify the tamper-evident hash chain of run traces")
    audit.add_argument("path", nargs="?", help="a single trace file (default: audit all under runs/)")
    audit.add_argument("--json", action="store_true", help="emit the audit report as JSON")
    audit.set_defaults(func=_cmd_audit)

    bench = sub.add_parser("bench", help="run offline benchmark/evaluation suites")
    bench.add_argument("suite", nargs="?", help="a single suite file (default: run all under benchmarks/)")
    bench.add_argument("--json", action="store_true", help="emit the evaluation report as JSON")
    bench.add_argument("--verbose", action="store_true", help="show every case, not just failures")
    bench.set_defaults(func=_cmd_bench)

    run = sub.add_parser("run", help="execute a plan as a bounded, checkpointed task DAG")
    run.add_argument("plan", nargs="?", help="path to a plan JSON file")
    run.add_argument("--run-id", default="run", help="run identifier (also the checkpoint dir)")
    run.add_argument("--resume", action="store_true", help="resume a checkpointed run by id")
    run.add_argument("--max-steps", type=int, help="override the step budget")
    run.add_argument("--max-seconds", type=float, help="override the wall-clock budget")
    run.add_argument("--max-retries", type=int, help="override the per-task retry budget")
    run.add_argument("--max-cost", type=float, help="override the cumulative cost budget")
    run.add_argument("--json", action="store_true", help="emit the final run state as JSON")
    run.set_defaults(func=_cmd_run)

    world = sub.add_parser("world", help="inspect or update typed world-state memory")
    world.add_argument("--list", action="store_true", help="print all facts as JSON")
    world.add_argument("--get", metavar="KEY", help="print a single fact as JSON")
    world.add_argument("--assert", dest="assert_key", metavar="KEY", help="record an observation")
    world.add_argument("--value", help="value for --assert (JSON for object/array types)")
    world.add_argument(
        "--type",
        default="string",
        choices=sorted(["string", "integer", "number", "boolean", "object", "array", "null"]),
        help="declared type of the asserted value",
    )
    world.add_argument("--source", default="cli", help="provenance source for --assert")
    world.add_argument(
        "--confidence", type=float, default=1.0, help="confidence in [0, 1] for --assert"
    )
    world.set_defaults(func=_cmd_world)

    return parser


def main(argv: list[str] | None = None) -> int:
    from .trace import Trace

    parser = build_parser()
    args = parser.parse_args(argv)
    func: Any = args.func
    with Trace(command=args.command) as trace:
        args.trace = trace
        code = func(args)
        trace.event("result", exit_code=code)
    return int(code)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
