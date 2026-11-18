"""Layer boundaries from ``docs/explanation/architecture.md``, enforced on the source.

A module may import only from its own layer or a lower one. A backward import
(for example ``routing`` importing ``cli``) fails here, so the layering in the
architecture document cannot erode silently. New modules must be assigned a
layer below, which keeps this table and the package in step.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "omniagi"

# Lower number = lower layer. Names follow the table in docs/explanation/architecture.md;
# ``selfcheck`` is the orchestrator that runs the verification checks.
LAYERS: dict[str, int] = {
    "__init__": 0,
    "paths": 0,
    "results": 0,
    "registry": 1,
    "docgen": 2,
    "integrity": 3,
    "constitution": 3,
    "hashing": 3,
    "memory": 3,
    "routing": 4,
    "health": 4,
    "shell": 5,
    "extend": 5,
    "adapters": 5,
    "selfcheck": 5,
    "trace": 6,
    "watchdog": 6,
    "cli": 7,
}


def internal_imports(source: str) -> set[str]:
    """Names of sibling ``omniagi`` modules imported anywhere in ``source``."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if node.level == 1:
                if node.module:
                    found.add(node.module.split(".")[0])
                else:
                    found.update(alias.name for alias in node.names)
            elif node.module and node.module.split(".")[0] == "omniagi" and node.level == 0:
                parts = node.module.split(".")
                if len(parts) > 1:
                    found.add(parts[1])
                else:
                    found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "omniagi" and len(parts) > 1:
                    found.add(parts[1])
    return found & set(LAYERS)


def violations(module: str, source: str) -> list[str]:
    return [
        f"{module} (layer {LAYERS[module]}) imports {dep} (layer {LAYERS[dep]})"
        for dep in sorted(internal_imports(source))
        if dep != module and LAYERS[dep] > LAYERS[module]
    ]


def test_every_module_is_assigned_a_layer() -> None:
    on_disk = {path.stem for path in PACKAGE.glob("*.py")}
    assert on_disk == set(LAYERS), f"unassigned or stale modules: {on_disk ^ set(LAYERS)}"


@pytest.mark.parametrize("module", sorted(LAYERS))
def test_module_imports_only_from_its_own_or_lower_layers(module: str) -> None:
    source = (PACKAGE / f"{module}.py").read_text(encoding="utf-8")
    assert violations(module, source) == []


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("routing", "from .cli import main\n"),
        ("routing", "def f():\n    from . import cli\n"),
        ("registry", "import omniagi.watchdog\n"),
        ("paths", "from omniagi.registry import load_registry\n"),
    ],
)
def test_a_backward_import_is_detected(module: str, source: str) -> None:
    """The detector itself must be able to fail, or the rule above proves nothing."""
    assert violations(module, source)
