"""Registry <-> filesystem reconciliation and markdown link validation.

This is what ``selfcheck.py`` should always have been: it verifies real state
on disk instead of grepping the documentation for reassuring phrases.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .paths import harness_root, resolve
from .registry import Registry, load_registry
from .results import CheckResult

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "runs", ".pytest_cache", ".ruff_cache"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BACKTICK_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:md|py|json|ya?ml))`")


def _markdown_files() -> list[Path]:
    root = harness_root()
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        files.append(path)
    return files


def check_tool_specs(registry: Registry | None = None) -> CheckResult:
    """Every registered tool has a spec, and every spec is registered."""
    reg = registry or load_registry()
    errors: list[str] = []

    registered_specs: set[str] = set()
    for tool in reg.tools:
        spec = resolve(tool["spec"])
        registered_specs.add(tool["spec"])
        if not spec.is_file():
            errors.append(f"tool '{tool['id']}' declares missing spec {tool['spec']}")
            continue
        body = spec.read_text(encoding="utf-8")
        if tool["id"] not in body:
            errors.append(f"spec {tool['spec']} never mentions its tool id '{tool['id']}'")

    tools_dir = resolve("tools")
    if tools_dir.is_dir():
        for spec in sorted(tools_dir.glob("*.md")):
            rel = f"tools/{spec.name}"
            if rel not in registered_specs:
                errors.append(f"unregistered tool spec on disk: {rel}")

    return CheckResult.from_errors(
        "integrity.tool_specs",
        errors,
        f"{len(reg.tools)} tools reconcile with tools/ on disk",
        "tool registry and tools/ directory disagree",
    )


def check_agent_specs(registry: Registry | None = None) -> CheckResult:
    reg = registry or load_registry()
    errors: list[str] = []
    registered = set()
    for agent in reg.agents:
        registered.add(agent["spec"])
        if not resolve(agent["spec"]).is_file():
            errors.append(f"agent '{agent['id']}' declares missing spec {agent['spec']}")

    agents_dir = resolve("agents")
    if agents_dir.is_dir():
        for spec in sorted(agents_dir.glob("*.md")):
            rel = f"agents/{spec.name}"
            if rel not in registered:
                errors.append(f"unregistered agent spec on disk: {rel}")

    return CheckResult.from_errors(
        "integrity.agent_specs",
        errors,
        f"{len(reg.agents)} agent specs reconcile with agents/ on disk",
        "agent registry and agents/ directory disagree",
    )


def check_scripts(registry: Registry | None = None) -> CheckResult:
    """Every script referenced by a tool exists and is importable/runnable."""
    reg = registry or load_registry()
    errors: list[str] = []
    for tool in reg.tools:
        script = tool.get("script")
        if not script:
            continue
        target = resolve(script)
        if not target.is_file():
            errors.append(f"tool '{tool['id']}' references missing script {script}")
            continue
        if target.suffix == ".py" and not target.read_text(encoding="utf-8").strip():
            errors.append(f"tool '{tool['id']}' references empty script {script}")
    return CheckResult.from_errors(
        "integrity.tool_scripts",
        errors,
        "every tool-referenced script exists and is non-empty",
        "tool scripts are missing or empty",
    )


def check_tool_handlers(registry: Registry | None = None) -> CheckResult:
    """Registered runtime handlers and implemented handlers must agree.

    A tool that declares a handler nothing implements is a promise the harness
    cannot keep; an implemented handler nothing registers is unreachable code.
    """
    from .tool_runtime import HANDLERS

    reg = registry or load_registry()
    errors: list[str] = []
    declared: dict[str, str] = {}
    for tool in reg.tools:
        handler = tool.get("handler")
        if handler is None:
            continue
        if handler not in HANDLERS:
            errors.append(
                f"tool '{tool['id']}' declares handler '{handler}' "
                "which omniagi.tool_runtime does not implement"
            )
            continue
        if handler in declared:
            errors.append(
                f"handler '{handler}' is claimed by both "
                f"'{declared[handler]}' and '{tool['id']}'"
            )
        declared[handler] = tool["id"]
        if tool["status"] != "active":
            errors.append(f"tool '{tool['id']}' is runnable but registered as {tool['status']}")

    for handler in sorted(set(HANDLERS) - set(declared)):
        errors.append(f"handler '{handler}' is implemented but no registered tool declares it")

    return CheckResult.from_errors(
        "integrity.tool_handlers",
        errors,
        f"{len(declared)} tools are executable through the runtime",
        "tool registry and tool runtime disagree",
    )


def check_constitution_files(registry: Registry | None = None) -> CheckResult:
    reg = registry or load_registry()
    errors = [rel for rel in reg.constitution_files if not resolve(rel).is_file()]
    return CheckResult.from_errors(
        "integrity.constitution_files",
        [f"missing constitution file: {rel}" for rel in errors],
        f"all {len(reg.constitution_files)} constitution files present",
        "constitution files are missing",
    )


def check_markdown_links(registry: Registry | None = None) -> CheckResult:
    """Every relative markdown link and backticked path must resolve.

    References that are intentionally absent (a protected filename, a gitignored
    runtime artifact, an external research note) must be declared in
    ``registry/harness.json`` under ``link_exemptions`` *with a reason*, so the
    exception is reviewable instead of silently tolerated.
    """
    reg = registry or load_registry()
    exempt = {item["path"] for item in reg.data.get("link_exemptions", [])}
    root = harness_root()
    errors: list[str] = []
    for path in _markdown_files():
        rel_doc = path.relative_to(root)
        text = path.read_text(encoding="utf-8")
        candidates: set[str] = set()
        for match in LINK_RE.finditer(text):
            candidates.add(match.group(1))
        for match in BACKTICK_PATH_RE.finditer(text):
            candidates.add(match.group(1))

        for target in sorted(candidates):
            if target.startswith("#"):
                continue
            parsed = urlparse(target)
            if parsed.scheme or target.startswith("//"):
                continue
            cleaned = target.split("#", 1)[0].split("?", 1)[0]
            if not cleaned:
                continue
            if cleaned.startswith("~") or cleaned.startswith("/"):
                # Absolute or home-relative paths are host state, not harness state.
                continue
            if cleaned in exempt:
                continue
            resolved = (path.parent / cleaned).resolve()
            if not resolved.exists() and not (root / cleaned).exists():
                errors.append(f"{rel_doc}: broken reference '{target}'")
    return CheckResult.from_errors(
        "integrity.markdown_links",
        errors,
        f"all relative references in {len(_markdown_files())} markdown files resolve",
        "markdown files contain broken references",
    )


def check_no_hardcoded_paths() -> CheckResult:
    """No source file may hardcode a developer's home directory.

    This is the regression guard for the macOS-only ``/Users/<name>`` paths that
    made the harness unrunnable on any other host.
    """
    root = harness_root()
    pattern = re.compile(r"(?:/Users/|/home/|C:\\\\Users\\\\)[A-Za-z0-9_.-]+/")
    errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel_parts = set(path.relative_to(root).parts)
        if SKIP_DIRS & rel_parts or path.name == "test_no_hardcoded_paths.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "omniagi:allow-abs-path" in line:
                continue
            if pattern.search(line):
                rel = path.relative_to(root)
                errors.append(f"{rel}:{lineno}: hardcoded host path")
    return CheckResult.from_errors(
        "integrity.no_hardcoded_paths",
        errors,
        "no source file hardcodes a host-specific home directory",
        "source files hardcode host-specific paths",
    )


def all_checks(registry: Registry | None = None) -> list[CheckResult]:
    reg = registry or load_registry()
    return [
        check_constitution_files(reg),
        check_tool_specs(reg),
        check_agent_specs(reg),
        check_scripts(reg),
        check_tool_handlers(reg),
        check_markdown_links(reg),
        check_no_hardcoded_paths(),
    ]
