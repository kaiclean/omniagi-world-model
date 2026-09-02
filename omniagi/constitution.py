"""Constitution-as-code.

Each of the five non-negotiables from ``OmniAGI.md`` is an individually named
check function, so a CI failure names the rule that broke instead of emitting an
undifferentiated ``RESULT: FAIL``.

The single-master rule in particular is now a *structural* invariant over the
registry and the spec files, not a grep for the phrase "sole master": a second
master could previously be added while the check still printed PASS.
"""

from __future__ import annotations

import re
from pathlib import Path

from .hashing import HashError, hash_file
from .paths import harness_root, resolve
from .registry import Registry, load_registry
from .results import CheckResult

# Declarations that only the constitution may make. Anything else claiming these
# is asserting mastership.
SELF_MASTER_PATTERNS: list[tuple[str, str]] = [
    (r"(?im)^\s*#{1,6}\s*master\s*$", "declares a '# Master' section"),
    (r"(?i)\bcount:\**\s*exactly\s*\d", "declares a master count"),
    (r"(?i)\byou are (?:the |a )?(?:sole |single |one |only )?master\b", "declares itself master"),
    (r"(?i)\bi am (?:the )?(?:sole |single )?master\b", "declares itself master"),
    (r"(?i)\bfull read/write over this harness\b", "claims harness-wide ownership rights"),
    (
        r"(?i)\bmay change routing, tools, memory, workflows\b",
        "claims constitutional amendment rights",
    ),
    (r"(?i)\bsecond master\b(?!\s*(?:agent)?\.?\s*$)", "references a second master"),
]

SUBORDINATION_MARKER = "Owned subroutine of OmniAGI"


def _spec_files(reg: Registry) -> list[Path]:
    """Every markdown spec that is *not* part of the constitution."""
    root = harness_root()
    constitution = {resolve(rel).resolve() for rel in reg.constitution_files}
    constitution.add(resolve(reg.master["spec"]).resolve())
    constitution.add(resolve(reg.master["constitution"]).resolve())
    files: list[Path] = []
    for directory in ("agents", "tools", "harnesses", "references", "workflows"):
        target = resolve(directory)
        if not target.is_dir():
            continue
        for path in sorted(target.glob("*.md")):
            if path.resolve() in constitution:
                continue
            files.append(path)
    _ = root
    return files


# -- non-negotiable 1 ----------------------------------------------------------


def check_single_master(registry: Registry | None = None) -> CheckResult:
    """Exactly one master exists, and nothing else claims mastership."""
    reg = registry or load_registry()
    errors: list[str] = []

    masters = [reg.master] if reg.master.get("role") == "master" else []
    masters.extend(agent for agent in reg.agents if agent.get("role") == "master")
    if len(masters) != 1:
        errors.append(
            f"registry declares {len(masters)} entities with role 'master'; exactly 1 is required"
        )

    for agent in reg.agents:
        if agent.get("role") != "specialist":
            errors.append(f"agent '{agent['id']}' has role '{agent.get('role')}', expected 'specialist'")
        if agent["id"] == reg.master["id"]:
            errors.append(f"agent '{agent['id']}' collides with the master id")

    # The constitution must still name the master and pin the count.
    constitution_text = resolve(reg.master["constitution"]).read_text(encoding="utf-8")
    if reg.master["name"] not in constitution_text:
        errors.append(
            f"{reg.master['constitution']} does not name the registered master '{reg.master['name']}'"
        )
    if not re.search(r"(?i)count:\**\s*exactly\s*1", constitution_text):
        errors.append(f"{reg.master['constitution']} no longer pins the master count to exactly 1")

    for path in _spec_files(reg):
        rel = path.relative_to(harness_root())
        text = path.read_text(encoding="utf-8")
        for pattern, reason in SELF_MASTER_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{rel}: {reason} - only the constitution may do that")

    for agent in reg.agents:
        spec = resolve(agent["spec"])
        if spec.is_file() and SUBORDINATION_MARKER not in spec.read_text(encoding="utf-8"):
            errors.append(
                f"{agent['spec']}: missing subordination marker '{SUBORDINATION_MARKER}'"
            )

    return CheckResult.from_errors(
        "constitution.single_master",
        errors,
        f"exactly one master ({reg.master['name']}); {len(reg.agents)} subordinate specialists",
        "single-master invariant violated",
    )


# -- non-negotiable 2 ----------------------------------------------------------


def check_no_simulated_success(registry: Registry | None = None) -> CheckResult:
    """Tools must fail loudly; success sentinels are forbidden.

    This check *executes* the failure path rather than reading about it.
    """
    reg = registry or load_registry()
    errors: list[str] = []

    # 1. The hasher must raise on a missing file instead of returning a string.
    try:
        result = hash_file("this-file-does-not-exist-omniagi-check")
    except HashError:
        pass
    else:
        errors.append(
            f"file_hasher returned {result!r} for a missing file instead of failing loudly"
        )

    # 2. And it must return a real 64-char digest for a file that does exist.
    digest = hash_file(reg.master["spec"])
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"file_hasher returned a malformed digest for {reg.master['spec']}")

    # 3. No harness module may return an error message as if it were a value.
    sentinel = re.compile(r"return\s+[\"']\s*(?:Error|error|FAILED|N/A)")
    package = resolve("omniagi")
    for path in sorted(package.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if sentinel.search(line):
                errors.append(f"omniagi/{path.name}:{lineno}: returns an error sentinel as a value")

    # 4. The verification step must still exist in the agent loop.
    loop = resolve("workflows/agent-loop.md").read_text(encoding="utf-8")
    if "### 4. Verify" not in loop:
        errors.append("workflows/agent-loop.md no longer contains an explicit Verify step")

    return CheckResult.from_errors(
        "constitution.no_simulated_success",
        errors,
        "tools fail loudly; no error sentinels are returned as values",
        "a tool can report success without evidence",
    )


# -- non-negotiable 3 ----------------------------------------------------------


def check_tool_extension_protocol(registry: Registry | None = None) -> CheckResult:
    """The self-extension protocol is documented, registered and implemented."""
    reg = registry or load_registry()
    errors: list[str] = []

    workflow = resolve("workflows/tool-extension.md")
    if not workflow.is_file():
        errors.append("workflows/tool-extension.md is missing")
    else:
        text = workflow.read_text(encoding="utf-8")
        for step in ("Detect", "Specify", "Implement", "Register", "Verify", "Log"):
            if step not in text:
                errors.append(f"workflows/tool-extension.md is missing the '{step}' step")

    if reg.tool("tool_register") is None:
        errors.append("the tool_register tool is not in the registry")
    if not resolve("omniagi/extend.py").is_file():
        errors.append("omniagi/extend.py (the protocol implementation) is missing")

    return CheckResult.from_errors(
        "constitution.tool_extension_protocol",
        errors,
        "the self-extension protocol is documented and implemented",
        "the self-extension protocol is incomplete",
    )


# -- non-negotiable 4 ----------------------------------------------------------


def check_smallest_patch(registry: Registry | None = None) -> CheckResult:
    """Capability changes must be a one-place edit, not an N-file rewrite.

    The rule "prefer the smallest patch" is only enforceable if the harness is
    structured so a small patch is possible: every derived table must be
    generated from the registry, otherwise adding one tool means editing three
    files by hand and drifting two of them.
    """
    from .docgen import BLOCKS

    reg = registry or load_registry()
    errors: list[str] = []

    omni = resolve(reg.master["spec"]).read_text(encoding="utf-8")
    if "smallest patch" not in omni.lower():
        errors.append(f"{reg.master['spec']} no longer states the smallest-patch rule")

    derived_docs = {"TOOLS.md", "references/tools-registry.md", "references/agent-specs-summary.md"}
    missing = derived_docs - set(BLOCKS)
    for doc in sorted(missing):
        errors.append(f"{doc} duplicates registry data but is not generated from it")

    return CheckResult.from_errors(
        "constitution.smallest_patch",
        errors,
        "registry-derived documentation is generated, so capability edits stay small",
        "documentation duplicates the registry by hand",
    )


# -- non-negotiable 5 ----------------------------------------------------------


def check_read_before_act(registry: Registry | None = None) -> CheckResult:
    """The agent loop must order understanding before mutation."""
    reg = registry or load_registry()
    errors: list[str] = []

    loop_path = resolve("workflows/agent-loop.md")
    if not loop_path.is_file():
        errors.append("workflows/agent-loop.md is missing")
    else:
        text = loop_path.read_text(encoding="utf-8")
        expected = ["Understand", "Plan", "Execute", "Verify"]
        positions = []
        for phase in expected:
            match = re.search(rf"(?m)^###\s*\d+\.\s*{phase}\b", text)
            if match is None:
                errors.append(f"workflows/agent-loop.md is missing the '{phase}' phase")
            else:
                positions.append((phase, match.start()))
        ordered = [phase for phase, _ in sorted(positions, key=lambda item: item[1])]
        if ordered != [phase for phase in expected if phase in ordered]:
            errors.append(f"agent-loop phases are out of order: {ordered}")

    boot = resolve(reg.master["spec"]).read_text(encoding="utf-8")
    if "Boot sequence" not in boot:
        errors.append(f"{reg.master['spec']} no longer defines a boot (read-first) sequence")

    return CheckResult.from_errors(
        "constitution.read_before_act",
        errors,
        "the agent loop reads and plans before it mutates",
        "the read-before-act ordering is broken",
    )


CHECKS = {
    "check_single_master": check_single_master,
    "check_no_simulated_success": check_no_simulated_success,
    "check_tool_extension_protocol": check_tool_extension_protocol,
    "check_smallest_patch": check_smallest_patch,
    "check_read_before_act": check_read_before_act,
}


def all_checks(registry: Registry | None = None) -> list[CheckResult]:
    """Run every non-negotiable declared in the registry, in declared order."""
    reg = registry or load_registry()
    results: list[CheckResult] = []
    for rule in reg.non_negotiables:
        func = CHECKS.get(rule["check"])
        if func is None:
            results.append(
                CheckResult.failed(
                    f"constitution.{rule['id']}",
                    f"non-negotiable '{rule['id']}' declares unimplemented check '{rule['check']}'",
                )
            )
            continue
        results.append(func(reg))
    return results
