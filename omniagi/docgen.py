"""Generate markdown from the canonical registry.

Any table that describes tools, agents, seats or routing is a *build artifact*.
Generated regions are delimited by markers::

    <!-- omniagi:generated:start id=tools-table -->
    ...generated...
    <!-- omniagi:generated:end id=tools-table -->

``omniagi docs --check`` fails when a generated region is stale, which makes
registry/markdown drift a CI failure rather than a slow rot.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .paths import resolve
from .registry import Registry, load_registry
from .results import CheckResult

START = "<!-- omniagi:generated:start id={id} -->"
END = "<!-- omniagi:generated:end id={id} -->"

_BLOCK_RE = (
    r"(?P<start><!-- omniagi:generated:start id={id} -->)"
    r"(?P<body>.*?)"
    r"(?P<end><!-- omniagi:generated:end id={id} -->)"
)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


# -- individual block renderers ------------------------------------------------


def render_tools_table(reg: Registry) -> str:
    rows = [
        [
            f"`{tool['id']}`",
            tool["name"],
            f"`{tool['spec']}`",
            tool["status"],
            f"`{tool['handler']}`" if tool.get("handler") else "spec only",
            tool["notes"],
        ]
        for tool in reg.tools
    ]
    return _table(["ID", "Tool", "Spec", "Status", "Runtime", "Notes"], rows)


def render_tools_reference(reg: Registry) -> str:
    return "\n".join(f"- `{tool['id']}`: {tool['name']}." for tool in reg.tools)


def render_agents_table(reg: Registry) -> str:
    rows = []
    for agent in reg.agents:
        seat = reg.seat(agent["default_seat"])
        engine = seat["engine"] if seat else agent["default_seat"]
        rows.append([f"`{agent['id']}`", agent["purpose"], engine, f"`{agent['spec']}`"])
    return _table(["ID", "Role", "Default engine seat", "Spec"], rows)


def render_agents_reference(reg: Registry) -> str:
    return "\n".join(f"- **{agent['id']}:** {agent['purpose']}." for agent in reg.agents)


def render_seats_reference(reg: Registry) -> str:
    seats = sorted(reg.seats, key=lambda s: s["rank"])
    return "\n".join(f"{seat['rank']}. {seat['engine']} — {seat['role']}." for seat in seats)


def render_seats_provenance(reg: Registry) -> str:
    seats = sorted(reg.seats, key=lambda s: s["rank"])
    rows = [
        [
            str(seat["rank"]),
            seat["engine"],
            seat["tier"],
            seat["status"],
            seat["confidence"],
            seat["provenance"]["benchmark"],
            seat["provenance"]["source"],
            seat["provenance"]["verified_on"],
        ]
        for seat in seats
    ]
    return _table(
        ["#", "Engine", "Tier", "Status", "Confidence", "Benchmark / basis", "Source", "Verified on"],
        rows,
    )


def render_routing_table(reg: Registry) -> str:
    rows = []
    for rule in sorted(reg.routing["rules"], key=lambda r: r["priority"]):
        seat = reg.seat(rule["seat"])
        engine = seat["engine"] if seat else rule["seat"]
        top = sorted(rule["keywords"].items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        signals = ", ".join(f"{word} ({weight:g})" for word, weight in top)
        rows.append([str(rule["priority"]), f"`{rule['specialist']}`", engine, signals])
    default = reg.routing["default"]
    default_seat = reg.seat(default["seat"])
    rows.append(
        [
            "—",
            f"`{default['specialist']}` (default)",
            default_seat["engine"] if default_seat else default["seat"],
            default["rationale"],
        ]
    )
    return _table(["Priority", "Specialist", "Engine seat", "Top weighted signals"], rows)


def render_escalation_ladder(reg: Registry) -> str:
    esc = reg.escalation
    steps = []
    for index, seat_id in enumerate(esc["ladder"], start=1):
        seat = reg.seat(seat_id)
        engine = seat["engine"] if seat else seat_id
        cost = seat["relative_cost"] if seat else "?"
        steps.append(f"{index}. {engine} (relative cost {cost})")
    body = "\n".join(steps)
    return (
        f"Escalate when routing confidence < {esc['confidence_threshold']:g} or a step "
        f"fails, up to {esc['max_attempts']} attempts:\n\n{body}"
    )


def render_non_negotiables(reg: Registry) -> str:
    return "\n".join(
        f"{index}. **{item['id']}** — {item['statement']} (enforced by `{item['check']}`)"
        for index, item in enumerate(reg.non_negotiables, start=1)
    )


# -- block registry ------------------------------------------------------------

Renderer = Callable[[Registry], str]

BLOCKS: dict[str, list[tuple[str, Renderer]]] = {
    "TOOLS.md": [("tools-table", render_tools_table)],
    "WORLD_AGENTS.md": [
        ("agents-table", render_agents_table),
        ("non-negotiables", render_non_negotiables),
    ],
    "workflows/model-routing.md": [
        ("routing-table", render_routing_table),
        ("escalation-ladder", render_escalation_ladder),
    ],
    "harnesses/TOP10_AGENTIC_MOE.md": [("seats-provenance", render_seats_provenance)],
    "references/tools-registry.md": [("tools-reference", render_tools_reference)],
    "references/agent-specs-summary.md": [("agents-reference", render_agents_reference)],
    "references/top10-moe-engines.md": [("seats-reference", render_seats_reference)],
}


def _replace_block(text: str, block_id: str, body: str) -> tuple[str, bool]:
    pattern = re.compile(_BLOCK_RE.format(id=re.escape(block_id)), re.DOTALL)
    match = pattern.search(text)
    if match is None:
        raise DocgenError(f"missing generated block '{block_id}'")
    replacement = f"{match.group('start')}\n{body.strip()}\n{match.group('end')}"
    new_text = text[: match.start()] + replacement + text[match.end() :]
    return new_text, new_text != text


class DocgenError(RuntimeError):
    """Raised when a generated block marker is missing or malformed."""


def render_file(rel_path: str, reg: Registry) -> str:
    target = resolve(rel_path)
    if not target.exists():
        raise DocgenError(f"generated-doc target missing: {rel_path}")
    text = target.read_text(encoding="utf-8")
    for block_id, renderer in BLOCKS[rel_path]:
        text, _ = _replace_block(text, block_id, renderer(reg))
    return text


def generate(check_only: bool = False, registry: Registry | None = None) -> list[str]:
    """Regenerate every managed block.

    Returns the list of harness-relative paths that are (or would be) changed.
    """
    reg = registry or load_registry()
    changed: list[str] = []
    for rel_path in sorted(BLOCKS):
        target: Path = resolve(rel_path)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        rendered = render_file(rel_path, reg)
        if rendered != current:
            changed.append(rel_path)
            if not check_only:
                target.write_text(rendered, encoding="utf-8")
    return changed


def check_docs(registry: Registry | None = None) -> CheckResult:
    """Fail when any generated markdown block is stale."""
    name = "integrity.generated_docs"
    try:
        stale = generate(check_only=True, registry=registry)
    except DocgenError as exc:
        return CheckResult.failed(name, str(exc))
    return CheckResult.from_errors(
        name,
        [f"stale generated block in {path}" for path in stale],
        "generated markdown matches the registry",
        "generated markdown is stale - run 'omniagi docs'",
    )
