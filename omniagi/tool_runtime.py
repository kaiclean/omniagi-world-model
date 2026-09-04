"""The tool runtime: registered tools that actually execute.

Until this module existed every tool in ``registry/harness.json`` had
``script: null`` — the registry described tools that nothing could invoke, so
"self-extension" only ever produced paperwork. Here a registered tool is a
callable with:

* **dispatch through the registry.** A tool runs only if it is registered,
  ``active`` and declares a ``handler`` that exists in :data:`HANDLERS`.
* **schema validation.** Arguments are validated against a declared input
  schema before the handler is entered; unknown keys are rejected.
* **a timeout.** Every invocation runs under a wall-clock deadline and reports
  ``timed_out`` honestly instead of hanging the loop.
* **a JSON result.** Success and failure are both machine-readable
  :class:`ToolResult` documents; a failure is never rendered as a success.

Containment: ``file_read``/``file_write`` may only touch paths inside the
harness root, and ``shell`` delegates to :mod:`omniagi.shell` (argv form,
allowlisted executables, no shell interpolation).
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import shell
from .paths import harness_root
from .registry import Registry, load_registry

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = shell.MAX_TIMEOUT_SECONDS
MAX_READ_BYTES = 1_000_000

class ToolError(RuntimeError):
    """Raised when a tool cannot be dispatched or its arguments are invalid."""


@dataclass(frozen=True)
class ToolResult:
    """Machine-readable outcome of one tool invocation."""

    tool: str
    ok: bool
    args: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timed_out: bool = False
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "args": dict(self.args),
            "result": dict(self.result),
            "error": self.error,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
        }


# -- a deliberately small JSON-Schema subset -----------------------------------
#
# ``jsonschema`` is an optional dependency and the runtime must work without it,
# so argument validation uses the subset actually needed by the tool schemas.

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _check_type(value: Any, expected: str, where: str) -> None:
    types = _TYPES.get(expected)
    if types is None:  # pragma: no cover - defensive
        raise ToolError(f"unsupported schema type {expected!r} for {where}")
    if expected in ("integer", "number") and isinstance(value, bool):
        raise ToolError(f"{where} must be {expected}, got boolean")
    if not isinstance(value, types):
        raise ToolError(f"{where} must be {expected}, got {type(value).__name__}")


def validate_args(schema: dict[str, Any], args: dict[str, Any], tool_id: str) -> dict[str, Any]:
    """Validate ``args`` against ``schema`` and return a normalised copy."""
    if not isinstance(args, dict):
        raise ToolError(f"tool '{tool_id}' arguments must be a JSON object")

    properties: dict[str, Any] = schema.get("properties", {})
    unknown = sorted(set(args) - set(properties))
    if unknown:
        raise ToolError(
            f"tool '{tool_id}' got unknown argument(s): {', '.join(unknown)}; "
            f"accepted: {', '.join(sorted(properties))}"
        )

    missing = sorted(name for name in schema.get("required", []) if name not in args)
    if missing:
        raise ToolError(f"tool '{tool_id}' is missing required argument(s): {', '.join(missing)}")

    normalised: dict[str, Any] = {}
    for name, spec in properties.items():
        if name not in args:
            if "default" in spec:
                normalised[name] = spec["default"]
            continue
        value = args[name]
        where = f"tool '{tool_id}' argument '{name}'"
        _check_type(value, spec["type"], where)
        if spec["type"] == "array":
            item_type = spec.get("items", {}).get("type")
            if item_type:
                for index, item in enumerate(value):
                    _check_type(item, item_type, f"{where}[{index}]")
            if len(value) < spec.get("minItems", 0):
                raise ToolError(f"{where} needs at least {spec['minItems']} item(s)")
        if spec["type"] == "string" and len(value) < spec.get("minLength", 0):
            raise ToolError(f"{where} must be at least {spec['minLength']} character(s)")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolError(f"{where} must be one of {', '.join(map(str, spec['enum']))}")
        if "minimum" in spec and value < spec["minimum"]:
            raise ToolError(f"{where} must be >= {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            raise ToolError(f"{where} must be <= {spec['maximum']}")
        normalised[name] = value
    return normalised


# -- path containment ----------------------------------------------------------


def _contained_path(raw: str, where: str) -> Path:
    """Resolve ``raw`` inside the harness root or refuse."""
    root = harness_root()
    candidate = Path(raw).expanduser()
    target = (root / candidate if not candidate.is_absolute() else candidate).resolve()
    if target != root and root not in target.parents:
        raise ToolError(f"{where} escapes the harness root: {raw}")
    return target


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- handlers ------------------------------------------------------------------


def handle_file_read(args: dict[str, Any]) -> dict[str, Any]:
    path = _contained_path(args["path"], "file_read path")
    if not path.is_file():
        raise ToolError(f"file_read: not a file: {args['path']}")
    limit = int(args["max_bytes"])
    data = path.read_bytes()
    truncated = len(data) > limit
    body = data[:limit]
    return {
        "path": str(path),
        "bytes": len(data),
        "truncated": truncated,
        "sha256": _sha256(data),
        "content": body.decode("utf-8", errors="replace"),
    }


def handle_file_write(args: dict[str, Any]) -> dict[str, Any]:
    path = _contained_path(args["path"], "file_write path")
    if ".git" in path.relative_to(harness_root()).parts:
        raise ToolError("file_write: refusing to write inside .git")
    if path.exists() and not args["overwrite"]:
        raise ToolError(f"file_write: {args['path']} exists and overwrite is false")
    if not path.parent.is_dir():
        if not args["create_parents"]:
            raise ToolError(f"file_write: parent directory does not exist: {path.parent}")
        path.parent.mkdir(parents=True, exist_ok=True)

    content: str = args["content"]
    path.write_text(content, encoding="utf-8")

    # Read-back verification: a write is not reported as successful until the
    # bytes on disk hash to what we intended to write.
    written = path.read_bytes()
    expected = content.encode("utf-8")
    if written != expected:
        raise ToolError(f"file_write: read-back mismatch for {args['path']}")
    return {
        "path": str(path),
        "bytes_written": len(written),
        "sha256": _sha256(written),
        "verified": True,
    }


def handle_shell(args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = shell.run(
            argv=args["argv"],
            workdir=args.get("workdir"),
            timeout=float(args["timeout"]),
        )
    except shell.ShellError as exc:
        raise ToolError(f"shell: {exc}") from exc
    return result.to_dict()


@dataclass(frozen=True)
class ToolSpec:
    """A runtime-callable tool: input schema plus handler."""

    schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    #: Result key that must be truthy for the invocation to count as a success.
    #: Without it a non-zero exit status would be reported as "ok", which is
    #: precisely the ``no_simulated_success`` failure mode.
    ok_key: str | None = None


HANDLERS: dict[str, ToolSpec] = {
    "file_read": ToolSpec(
        schema={
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "max_bytes": {
                    "type": "integer",
                    "default": 100_000,
                    "minimum": 1,
                    "maximum": MAX_READ_BYTES,
                },
            },
        },
        handler=handle_file_read,
    ),
    "file_write": ToolSpec(
        schema={
            "type": "object",
            "required": ["path", "content"],
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean", "default": True},
                "create_parents": {"type": "boolean", "default": False},
            },
        },
        handler=handle_file_write,
    ),
    "shell": ToolSpec(
        schema={
            "type": "object",
            "required": ["argv"],
            "properties": {
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "workdir": {"type": "string", "minLength": 1},
                "timeout": {
                    "type": "number",
                    "default": shell.DEFAULT_TIMEOUT_SECONDS,
                    "minimum": 0.1,
                    "maximum": MAX_TIMEOUT_SECONDS,
                },
            },
        },
        handler=handle_shell,
        timeout=shell.MAX_TIMEOUT_SECONDS,
        ok_key="ok",
    ),
}


def runnable_tools(registry: Registry | None = None) -> list[dict[str, Any]]:
    """Registered tools that can actually be executed, with their schemas."""
    reg = registry or load_registry()
    runnable = []
    for tool in reg.tools:
        handler = tool.get("handler")
        if not handler or handler not in HANDLERS:
            continue
        runnable.append(
            {
                "id": tool["id"],
                "name": tool["name"],
                "status": tool["status"],
                "handler": handler,
                "schema": HANDLERS[handler].schema,
            }
        )
    return runnable


def resolve_tool(tool_id: str, registry: Registry | None = None) -> ToolSpec:
    """Look ``tool_id`` up in the registry and return its runtime spec."""
    reg = registry or load_registry()
    entry = reg.tool(tool_id)
    if entry is None:
        raise ToolError(f"unknown tool '{tool_id}' - it is not in the registry")
    if entry["status"] != "active":
        raise ToolError(f"tool '{tool_id}' is {entry['status']}, not active")
    handler = entry.get("handler")
    if not handler:
        raise ToolError(
            f"tool '{tool_id}' is registered but has no runtime handler - "
            "it is a specification, not an executable tool"
        )
    spec = HANDLERS.get(handler)
    if spec is None:
        raise ToolError(f"tool '{tool_id}' declares unknown handler '{handler}'")
    return spec


def run_tool(
    tool_id: str,
    args: dict[str, Any] | None = None,
    registry: Registry | None = None,
    timeout: float | None = None,
) -> ToolResult:
    """Validate and execute one registered tool. Never raises for tool failure."""
    supplied = dict(args or {})
    started = time.monotonic()

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        spec = resolve_tool(tool_id, registry=registry)
        validated = validate_args(spec.schema, supplied, tool_id)
    except ToolError as exc:
        return ToolResult(tool=tool_id, ok=False, args=supplied, error=str(exc),
                          duration_ms=elapsed_ms())

    deadline = spec.timeout if timeout is None else float(timeout)
    if deadline <= 0 or deadline > MAX_TIMEOUT_SECONDS:
        return ToolResult(
            tool=tool_id,
            ok=False,
            args=validated,
            error=f"timeout must be in (0, {MAX_TIMEOUT_SECONDS}]; got {deadline}",
            duration_ms=elapsed_ms(),
        )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(spec.handler, validated)
        try:
            payload = future.result(timeout=deadline)
        except FutureTimeout:
            future.cancel()
            return ToolResult(
                tool=tool_id,
                ok=False,
                args=validated,
                error=f"tool '{tool_id}' exceeded its {deadline}s timeout",
                timed_out=True,
                duration_ms=elapsed_ms(),
            )
        except ToolError as exc:
            return ToolResult(tool=tool_id, ok=False, args=validated, error=str(exc),
                              duration_ms=elapsed_ms())
        except OSError as exc:
            return ToolResult(tool=tool_id, ok=False, args=validated, error=f"{tool_id}: {exc}",
                              duration_ms=elapsed_ms())

    ok = True
    error: str | None = None
    if spec.ok_key is not None and not payload.get(spec.ok_key):
        ok = False
        error = f"tool '{tool_id}' reported failure: " + str(
            payload.get("stderr") or payload.get("error") or f"{spec.ok_key} is false"
        ).strip()
    return ToolResult(
        tool=tool_id,
        ok=ok,
        args=validated,
        result=payload,
        error=error,
        timed_out=bool(payload.get("timed_out", False)),
        duration_ms=elapsed_ms(),
    )
