"""The closed agent loop: prompt → route → seat call → tools → verify → log.

``workflows/agent-loop.md`` described this loop; nothing executed it. This
module runs it end to end:

1. **route** — score the prompt, pick a specialist and an engine seat
2. **call** — ask the seat for a plan through :mod:`omniagi.adapters`
3. **act** — execute the tool calls the model emitted, through the registry
   runtime in :mod:`omniagi.tool_runtime`
4. **verify** — a step counts as done only when at least one tool call ran and
   every call returned ``ok`` with real evidence
5. **log** — append one deduplicated changelog line recording the outcome,
   pass *or* fail

The model contract is deliberately tiny, so a 7B local model can satisfy it:
emit one or more JSON objects (bare or in a fenced ```json block) shaped like::

    {"tool": "file_write", "args": {"path": "notes.md", "content": "hi"}}

Transports
----------

:class:`SeatTransport` is the real path and refuses to invent output when no
seat is reachable. :class:`ScriptedTransport` replays a recorded reply and
marks the run ``model_source="scripted"`` so a replayed run can never be
mistaken for a live one — that distinction is the ``no_simulated_success``
rule, made structural.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import adapters, tool_runtime
from .memory import append_changelog
from .registry import Registry, load_registry
from .routing import Decision, route
from .tool_runtime import ToolResult

MAX_TOOL_CALLS = 8

_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>.*?)```", re.DOTALL)


class LoopError(RuntimeError):
    """Raised when the loop cannot start (no seat, bad prompt)."""


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopResult:
    """Everything one pass of the loop did, and whether it is verified."""

    task: str
    decision: Decision
    model_source: str
    model_content: str
    calls: list[ToolResult] = field(default_factory=list)
    verified: bool = False
    verdict: str = ""
    logged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "route": {
                "specialist": self.decision.specialist,
                "seat": self.decision.seat,
                "engine": self.decision.engine,
                "confidence": round(self.decision.confidence, 4),
            },
            "model_source": self.model_source,
            "model_content": self.model_content,
            "calls": [call.to_dict() for call in self.calls],
            "verified": self.verified,
            "verdict": self.verdict,
            "logged": self.logged,
        }


class Transport(Protocol):
    """Anything that can turn a prompt into model text."""

    source: str

    def __call__(self, prompt: str, decision: Decision) -> str: ...


@dataclass
class SeatTransport:
    """The real path: call the routed seat, or raise."""

    registry: Registry | None = None
    probe_network: bool = False
    source: str = "seat"

    def __call__(self, prompt: str, decision: Decision) -> str:
        try:
            response = adapters.call_with_fallback(
                prompt,
                preferred_seat=decision.seat,
                registry=self.registry,
                probe_network=self.probe_network,
            )
        except adapters.SeatUnavailable as exc:
            raise LoopError(str(exc)) from exc
        self.source = f"seat:{response.seat}"
        return response.content


@dataclass
class ScriptedTransport:
    """Replay a recorded reply. Never presented as a live model call."""

    replies: Sequence[str]
    source: str = "scripted"
    _index: int = 0

    def __call__(self, prompt: str, decision: Decision) -> str:
        if self._index >= len(self.replies):
            raise LoopError("scripted transport ran out of recorded replies")
        reply = self.replies[self._index]
        self._index += 1
        return reply


def _iter_json_objects(text: str) -> list[Any]:
    """Yield every top-level JSON object found in ``text``."""
    found: list[Any] = []
    decoder = json.JSONDecoder()
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            return found
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        found.append(value)
        index = end


def parse_tool_calls(content: str) -> list[ToolCall]:
    """Extract tool calls from model text.

    Fenced blocks win when present; otherwise the whole message is scanned for
    JSON objects. Objects without a ``tool`` key are ignored rather than
    guessed at.
    """
    blocks = [match.group("body") for match in _FENCE_RE.finditer(content)]
    haystacks = blocks or [content]

    calls: list[ToolCall] = []
    for haystack in haystacks:
        for value in _iter_json_objects(haystack):
            if isinstance(value, dict) and "tool_calls" in value:
                candidates = value["tool_calls"]
            else:
                candidates = [value]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                name = candidate.get("tool") or candidate.get("name")
                if not isinstance(name, str) or not name:
                    continue
                args = candidate.get("args", candidate.get("arguments", {}))
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"__unparseable__": args}
                calls.append(ToolCall(tool=name, args=args if isinstance(args, dict) else {}))
    return calls


def build_prompt(task: str, decision: Decision, registry: Registry | None = None) -> str:
    """The instruction sent to the seat, including the callable tool schemas."""
    reg = registry or load_registry()
    tools = tool_runtime.runnable_tools(reg)
    catalogue = json.dumps(
        [{"tool": tool["id"], "args_schema": tool["schema"]} for tool in tools], indent=2
    )
    return (
        f"Task: {task}\n\n"
        f"You are acting as the '{decision.specialist}' specialist.\n"
        "Reply with ONLY a fenced ```json block containing one JSON object per line-delimited "
        'array entry, each shaped {"tool": <id>, "args": {...}}. '
        "Use only these tools; any other name is rejected by the runtime:\n"
        f"{catalogue}\n\n"
        "Do not claim a step succeeded: the harness executes your calls and verifies them."
    )


def run_loop(
    task: str,
    transport: Transport | None = None,
    registry: Registry | None = None,
    log: bool = True,
    max_calls: int = MAX_TOOL_CALLS,
) -> LoopResult:
    """Run one closed pass of the loop. Raises :class:`LoopError` on a blocker."""
    task = task.strip()
    if not task:
        raise LoopError("empty task")

    reg = registry or load_registry()
    decision = route(task, registry=reg)
    active: Transport = transport or SeatTransport(registry=reg)

    prompt = build_prompt(task, decision, registry=reg)
    content = active(prompt, decision)

    result = LoopResult(
        task=task,
        decision=decision,
        model_source=getattr(active, "source", "unknown"),
        model_content=content,
    )

    calls = parse_tool_calls(content)
    if len(calls) > max_calls:
        calls = calls[:max_calls]

    for call in calls:
        result.calls.append(tool_runtime.run_tool(call.tool, call.args, registry=reg))

    failures = [call for call in result.calls if not call.ok]
    if not result.calls:
        result.verified = False
        result.verdict = "no tool call was emitted - nothing was actually done"
    elif failures:
        result.verified = False
        first = failures[0]
        result.verdict = f"{len(failures)}/{len(result.calls)} tool call(s) failed: {first.error}"
    else:
        result.verified = True
        result.verdict = f"{len(result.calls)} tool call(s) executed and verified"

    if log:
        result.logged = append_changelog(
            f"loop: {task} | route={decision.specialist}/{decision.seat} "
            f"| source={result.model_source} | verified={result.verified} | {result.verdict}"
        )
    return result
