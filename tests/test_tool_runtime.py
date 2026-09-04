"""Tool-runtime tests.

The point of this module is that a registered tool *runs*. These tests execute
real file and shell operations inside a throwaway harness copy: nothing here is
mocked, because a mocked tool runtime would prove exactly nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omniagi import tool_runtime
from omniagi.tool_runtime import ToolError, run_tool


def test_the_registry_declares_the_implemented_handlers(registry) -> None:
    declared = {tool["handler"] for tool in registry.tools if tool.get("handler")}
    assert declared == set(tool_runtime.HANDLERS)


def test_runnable_tools_expose_their_schemas(registry) -> None:
    runnable = {tool["id"]: tool for tool in tool_runtime.runnable_tools(registry)}
    assert set(runnable) == {"file_read", "file_write", "shell"}
    assert runnable["file_write"]["schema"]["required"] == ["path", "content"]


# -- dispatch ------------------------------------------------------------------


def test_unregistered_tool_is_refused(temp_harness: Path) -> None:
    result = run_tool("definitely_not_a_tool", {})
    assert result.ok is False
    assert "unknown tool" in (result.error or "")


def test_specification_only_tool_is_refused(temp_harness: Path) -> None:
    """`web_search` is registered but has no handler: it must not pretend to run."""
    result = run_tool("web_search", {"query": "anything"})
    assert result.ok is False
    assert "no runtime handler" in (result.error or "")


# -- schema validation ---------------------------------------------------------


def test_missing_required_argument_fails_before_execution(temp_harness: Path) -> None:
    result = run_tool("file_write", {"path": "notes.md"})
    assert result.ok is False
    assert "missing required argument" in (result.error or "")
    assert not (temp_harness / "notes.md").exists()


def test_unknown_argument_is_rejected(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE", "sudo": True})
    assert result.ok is False
    assert "unknown argument" in (result.error or "")


def test_wrong_argument_type_is_rejected(temp_harness: Path) -> None:
    result = run_tool("shell", {"argv": "ls -la"})
    assert result.ok is False
    assert "must be array" in (result.error or "")


def test_defaults_are_applied(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE"})
    assert result.ok is True
    assert result.args["max_bytes"] == 100_000


def test_numeric_bounds_are_enforced(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE", "max_bytes": 0})
    assert result.ok is False
    assert ">=" in (result.error or "")


def test_booleans_are_not_accepted_as_integers(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE", "max_bytes": True})
    assert result.ok is False


# -- file_read / file_write ----------------------------------------------------


def test_file_write_then_read_round_trips(temp_harness: Path) -> None:
    written = run_tool(
        "file_write",
        {"path": "memory/scratch/a.md", "content": "hello\n", "create_parents": True},
    )
    assert written.ok is True
    assert written.result["verified"] is True

    read = run_tool("file_read", {"path": "memory/scratch/a.md"})
    assert read.ok is True
    assert read.result["content"] == "hello\n"
    assert read.result["sha256"] == written.result["sha256"]


def test_file_read_truncates_and_says_so(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE", "max_bytes": 10})
    assert result.ok is True
    assert result.result["truncated"] is True
    assert len(result.result["content"]) == 10


def test_file_read_on_a_directory_fails(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "memory"})
    assert result.ok is False
    assert "not a file" in (result.error or "")


def test_paths_may_not_escape_the_harness_root(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "../../../etc/hosts"})
    assert result.ok is False
    assert "escapes the harness root" in (result.error or "")


def test_writes_into_dot_git_are_refused(temp_harness: Path) -> None:
    (temp_harness / ".git").mkdir(exist_ok=True)
    result = run_tool("file_write", {"path": ".git/config", "content": "nope"})
    assert result.ok is False
    assert ".git" in (result.error or "")


def test_overwrite_false_protects_an_existing_file(temp_harness: Path) -> None:
    result = run_tool("file_write", {"path": "LICENSE", "content": "x", "overwrite": False})
    assert result.ok is False
    assert "exists" in (result.error or "")
    assert "MIT" in (temp_harness / "LICENSE").read_text(encoding="utf-8")


def test_missing_parent_directory_fails_unless_requested(temp_harness: Path) -> None:
    result = run_tool("file_write", {"path": "nope/deep/a.md", "content": "x"})
    assert result.ok is False
    assert "parent directory" in (result.error or "")


# -- shell ---------------------------------------------------------------------


def test_shell_runs_an_allowlisted_command(temp_harness: Path) -> None:
    result = run_tool("shell", {"argv": ["python3", "-c", "print('hi')"]})
    assert result.ok is True
    assert result.result["stdout"].strip() == "hi"
    assert result.result["exit_code"] == 0


def test_shell_reports_a_non_zero_exit_as_failure(temp_harness: Path) -> None:
    result = run_tool("shell", {"argv": ["python3", "-c", "raise SystemExit(3)"]})
    assert result.ok is False
    assert result.result["exit_code"] == 3


def test_shell_refuses_a_command_outside_the_allowlist(temp_harness: Path) -> None:
    result = run_tool("shell", {"argv": ["curl", "https://example.invalid"]})
    assert result.ok is False
    assert "not allowlisted" in (result.error or "")


def test_shell_timeout_is_reported_honestly(temp_harness: Path) -> None:
    result = run_tool(
        "shell",
        {"argv": ["python3", "-c", "import time; time.sleep(5)"], "timeout": 0.5},
    )
    assert result.ok is False
    assert result.timed_out is True


def test_runtime_level_timeout_stops_a_slow_tool(temp_harness: Path) -> None:
    result = run_tool(
        "shell",
        {"argv": ["python3", "-c", "import time; time.sleep(5)"]},
        timeout=0.5,
    )
    assert result.ok is False
    assert result.timed_out is True
    assert "timeout" in (result.error or "")


def test_an_absurd_timeout_is_rejected(temp_harness: Path) -> None:
    result = run_tool("file_read", {"path": "LICENSE"}, timeout=10_000)
    assert result.ok is False
    assert "timeout must be" in (result.error or "")


# -- result shape --------------------------------------------------------------


def test_every_result_is_json_serialisable(temp_harness: Path) -> None:
    import json

    for result in (
        run_tool("file_read", {"path": "LICENSE"}),
        run_tool("file_read", {"path": "no-such-file"}),
    ):
        payload = json.loads(json.dumps(result.to_dict()))
        assert set(payload) == {
            "tool",
            "ok",
            "args",
            "result",
            "error",
            "timed_out",
            "duration_ms",
        }


def test_resolve_tool_raises_for_an_unknown_tool(registry) -> None:
    with pytest.raises(ToolError):
        tool_runtime.resolve_tool("nope", registry=registry)
