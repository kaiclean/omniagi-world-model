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


def _cmd_tool(args: argparse.Namespace) -> int:
    from .tool_runtime import run_tool, runnable_tools

    if args.tool_action == "list":
        print(json.dumps(runnable_tools(), indent=2))
        return 0

    try:
        parsed = json.loads(args.args) if args.args else {}
    except json.JSONDecodeError as exc:
        print(f"error: --args is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(parsed, dict):
        print("error: --args must be a JSON object", file=sys.stderr)
        return 2

    result = run_tool(args.tool_id, parsed, timeout=args.timeout)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


def _cmd_loop(args: argparse.Namespace) -> int:
    from .loop import LoopError, ScriptedTransport, run_loop

    task = " ".join(args.task).strip()
    if not task:
        print("error: no task provided", file=sys.stderr)
        return 2

    transport = None
    if args.scripted:
        from pathlib import Path as _Path

        transport = ScriptedTransport(replies=[_Path(args.scripted).read_text(encoding="utf-8")])

    try:
        result = run_loop(task, transport=transport, log=not args.no_log)
    except LoopError as exc:
        print(f"blocker: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"task:       {result.task}")
        print(f"route:      {result.decision.specialist} -> {result.decision.engine}")
        print(f"model:      {result.model_source}")
        for call in result.calls:
            status = "ok" if call.ok else f"FAILED: {call.error}"
            print(f"  tool {call.tool} ({call.duration_ms}ms): {status}")
        print(f"verified:   {result.verified} ({result.verdict})")
        print(f"changelog:  {'appended' if result.logged else 'not written'}")
    return 0 if result.verified else 1


def _cmd_eval(args: argparse.Namespace) -> int:
    from .evaluate import FixtureError, evaluate, format_report

    try:
        report = evaluate(args.fixture)
    except FixtureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0 if report.ok else 1


def _cmd_seats(args: argparse.Namespace) -> int:
    from .health import probe_all

    results = [h.to_dict() for h in probe_all(probe_network=args.probe_network)]
    print(json.dumps(results, indent=2))
    return 0


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

    tool = sub.add_parser("tool", help="run a registered tool through the runtime")
    tool_sub = tool.add_subparsers(dest="tool_action", required=True)
    tool_list = tool_sub.add_parser("list", help="list executable tools and their argument schemas")
    tool_list.set_defaults(func=_cmd_tool)
    tool_run = tool_sub.add_parser("run", help="validate and execute one tool")
    tool_run.add_argument("tool_id")
    tool_run.add_argument("--args", default="{}", help="arguments as a JSON object")
    tool_run.add_argument("--timeout", type=float, default=None, help="override the tool timeout")
    tool_run.set_defaults(func=_cmd_tool)

    loop = sub.add_parser("loop", help="run the closed loop: route, call a seat, act, verify, log")
    loop.add_argument("task", nargs="+")
    loop.add_argument("--json", action="store_true")
    loop.add_argument("--no-log", action="store_true", help="do not append a changelog entry")
    loop.add_argument(
        "--scripted",
        metavar="FILE",
        help="replay a recorded model reply instead of calling a seat (marked as scripted)",
    )
    loop.set_defaults(func=_cmd_loop)

    evaluation = sub.add_parser("eval", help="score the task fixture: pass/fail per task")
    evaluation.add_argument("--fixture", help="path to a task fixture JSON file")
    evaluation.add_argument("--json", action="store_true")
    evaluation.set_defaults(func=_cmd_eval)

    seats = sub.add_parser("seats", help="probe engine-seat availability")
    seats.add_argument("--probe-network", action="store_true")
    seats.set_defaults(func=_cmd_seats)

    return parser


def main(argv: list[str] | None = None) -> int:
    from .trace import Trace

    parser = build_parser()
    args = parser.parse_args(argv)
    func: Any = args.func
    with Trace(command=args.command) as trace:
        code = func(args)
        trace.event("result", exit_code=code)
    return int(code)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
