"""Self-extension round-trip tests.

Every one of these runs the real protocol against a real temporary harness:
files are written and read back from disk. Nothing here is simulated, which is
the point of the protocol.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import docgen, extend
from omniagi.registry import load_registry, registry_path
from omniagi.results import Status
from omniagi.selfcheck import run_checks


def _add(tool_id: str = "line_counter") -> extend.ExtensionReport:
    return extend.extend_tool(
        tool_id=tool_id,
        name="Count lines in a harness file",
        purpose="Report the line count of a harness file",
    )


def test_round_trip_registers_and_verifies(temp_harness: Path) -> None:
    report = _add()
    assert report.verified is True
    assert len(report.steps) == 7

    assert (temp_harness / "tools" / "line_counter.md").is_file()
    assert load_registry().tool("line_counter") is not None
    assert "line_counter" in (temp_harness / "TOOLS.md").read_text(encoding="utf-8")


def test_round_trip_leaves_the_harness_verifiable(temp_harness: Path) -> None:
    """After extension, generated docs must not be stale and checks must hold."""
    _add()
    assert docgen.check_docs().status is Status.PASS

    report = run_checks()
    failures = [r.name for r in report.results if r.status is Status.FAIL]
    assert failures == [], failures


def test_round_trip_logs_exactly_one_changelog_line(temp_harness: Path) -> None:
    changelog = temp_harness / "memory" / "CHANGELOG.md"
    before = changelog.read_text(encoding="utf-8").splitlines()
    _add()
    after = changelog.read_text(encoding="utf-8").splitlines()
    assert len(after) == len(before) + 1
    assert "line_counter" in after[-1]


def test_registering_an_existing_tool_is_refused(temp_harness: Path) -> None:
    with pytest.raises(extend.ExtensionError) as excinfo:
        extend.extend_tool("file_hasher", "dup", "duplicate")
    assert "already registered" in str(excinfo.value)


def test_orphan_spec_blocks_registration(temp_harness: Path) -> None:
    """A spec on disk with no registration is a defect, not a starting point."""
    (temp_harness / "tools" / "line_counter.md").write_text("# stub\n", encoding="utf-8")
    with pytest.raises(extend.ExtensionError) as excinfo:
        _add()
    assert "unregistered" in str(excinfo.value)


@pytest.mark.parametrize("bad_id", ["Line-Counter", "line counter", "LineCounter", "line/counter", ""])
def test_invalid_tool_ids_are_refused(temp_harness: Path, bad_id: str) -> None:
    with pytest.raises(extend.ExtensionError):
        extend.extend_tool(bad_id, "x", "y")


def test_missing_script_aborts_and_leaves_no_partial_state(temp_harness: Path) -> None:
    with pytest.raises(extend.ExtensionError):
        extend.extend_tool("line_counter", "x", "y", script="omniagi/nope.py")

    assert not (temp_harness / "tools" / "line_counter.md").exists()
    data = json.loads(registry_path().read_text(encoding="utf-8"))
    assert all(tool["id"] != "line_counter" for tool in data["tools"])


def test_demo_runs_in_a_copy_and_never_touches_the_real_tree(repo_root: Path) -> None:
    report = extend.demo()
    assert report.verified is True
    assert report.root != str(repo_root)
    assert not (repo_root / "tools" / f"{extend.DEMO_TOOL_ID}.md").exists()
    assert extend.DEMO_TOOL_ID not in (repo_root / "TOOLS.md").read_text(encoding="utf-8")


def test_temporary_harness_restores_the_previous_root(repo_root: Path) -> None:
    from omniagi.paths import harness_root

    before = harness_root()
    with extend.temporary_harness() as temporary:
        assert harness_root() == temporary.resolve()
    assert harness_root() == before
