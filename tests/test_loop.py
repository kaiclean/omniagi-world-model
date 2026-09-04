"""Closed-loop and fixture-evaluation tests.

The loop is the P0 claim of this repository: prompt in, routed seat call, real
tool calls, verification, changelog. These tests run it end to end with a
recorded model reply, so every phase except the network hop is genuinely
executed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import evaluate, loop
from omniagi.loop import LoopError, ScriptedTransport, parse_tool_calls, run_loop

FIXTURE = Path(__file__).parent / "fixtures" / "loop_tasks.json"


def _reply(*calls: dict) -> str:
    return "```json\n" + json.dumps(list(calls)) + "\n```"


# -- parsing -------------------------------------------------------------------


def test_parses_a_fenced_tool_call() -> None:
    calls = parse_tool_calls(_reply({"tool": "file_read", "args": {"path": "LICENSE"}}))
    assert [(call.tool, call.args) for call in calls] == [("file_read", {"path": "LICENSE"})]


def test_parses_a_bare_json_object() -> None:
    calls = parse_tool_calls('sure: {"tool": "shell", "args": {"argv": ["ls"]}} done')
    assert calls[0].tool == "shell"


def test_parses_the_openai_style_name_arguments_shape() -> None:
    calls = parse_tool_calls('{"name": "file_read", "arguments": "{\\"path\\": \\"LICENSE\\"}"}')
    assert calls[0].tool == "file_read"
    assert calls[0].args == {"path": "LICENSE"}


def test_prose_without_tool_calls_parses_to_nothing() -> None:
    assert parse_tool_calls("I have already done it, trust me.") == []


def test_json_without_a_tool_key_is_ignored() -> None:
    assert parse_tool_calls('{"thought": "planning"}') == []


# -- the loop ------------------------------------------------------------------


def test_a_successful_pass_writes_a_file_and_verifies_it(temp_harness: Path) -> None:
    result = run_loop(
        "implement a scratch note",
        transport=ScriptedTransport(
            replies=[
                _reply(
                    {
                        "tool": "file_write",
                        "args": {
                            "path": "memory/scratch/note.md",
                            "content": "evidence\n",
                            "create_parents": True,
                        },
                    }
                )
            ]
        ),
    )
    assert result.verified is True
    assert result.model_source == "scripted"
    assert (temp_harness / "memory" / "scratch" / "note.md").read_text() == "evidence\n"
    assert result.logged is True
    changelog = (temp_harness / "memory" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "verified=True" in changelog


def test_a_failing_tool_call_is_never_reported_as_success(temp_harness: Path) -> None:
    result = run_loop(
        "run a command that fails",
        transport=ScriptedTransport(
            replies=[_reply({"tool": "shell", "args": {"argv": ["python3", "-c", "raise SystemExit(2)"]}})]
        ),
    )
    assert result.verified is False
    assert "failed" in result.verdict
    changelog = (temp_harness / "memory" / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "verified=False" in changelog


def test_a_reply_with_no_tool_call_is_not_verified(temp_harness: Path) -> None:
    result = run_loop(
        "explain the architecture",
        transport=ScriptedTransport(replies=["It is layered. Done."]),
    )
    assert result.verified is False
    assert "no tool call" in result.verdict


def test_the_loop_routes_before_it_acts(temp_harness: Path) -> None:
    result = run_loop(
        "refactor and debug the failing module",
        transport=ScriptedTransport(replies=["nothing"]),
        log=False,
    )
    assert result.decision.specialist == "coder"
    assert result.logged is False


def test_the_prompt_carries_the_callable_tool_schemas(temp_harness: Path) -> None:
    seen: list[str] = []

    class _Recorder:
        source = "scripted"

        def __call__(self, prompt: str, decision) -> str:
            seen.append(prompt)
            return "no calls"

    run_loop("write a file", transport=_Recorder(), log=False)
    assert "file_write" in seen[0]
    assert "args_schema" in seen[0]


def test_too_many_tool_calls_are_truncated(temp_harness: Path) -> None:
    calls = [{"tool": "file_read", "args": {"path": "LICENSE"}} for _ in range(5)]
    result = run_loop(
        "read it repeatedly",
        transport=ScriptedTransport(replies=[_reply(*calls)]),
        log=False,
        max_calls=2,
    )
    assert len(result.calls) == 2


def test_an_empty_task_is_refused(temp_harness: Path) -> None:
    with pytest.raises(LoopError):
        run_loop("   ", transport=ScriptedTransport(replies=["x"]))


def test_the_seat_transport_reports_a_blocker_instead_of_inventing_output(
    temp_harness: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omniagi import health

    for var in health.CLOUD_CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(LoopError) as excinfo:
        run_loop("do something real", transport=loop.SeatTransport(), log=False)
    assert "seat" in str(excinfo.value)


def test_scripted_transport_runs_out_of_replies(temp_harness: Path) -> None:
    transport = ScriptedTransport(replies=[])
    with pytest.raises(LoopError):
        run_loop("anything", transport=transport, log=False)


def test_result_is_json_serialisable(temp_harness: Path) -> None:
    result = run_loop(
        "read the license",
        transport=ScriptedTransport(replies=[_reply({"tool": "file_read", "args": {"path": "LICENSE"}})]),
        log=False,
    )
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["verified"] is True
    assert payload["route"]["specialist"]


# -- the fixture ---------------------------------------------------------------


def test_the_fixture_has_ten_tasks_with_both_outcomes() -> None:
    tasks = evaluate.load_fixture(FIXTURE)
    assert len(tasks) == 10
    outcomes = {task["expect"]["verified"] for task in tasks}
    assert outcomes == {True, False}


def test_every_fixture_task_behaves_as_specified() -> None:
    report = evaluate.evaluate(FIXTURE)
    failures = {outcome.task_id: outcome.reasons for outcome in report.failed}
    assert not failures, failures
    assert len(report.outcomes) == 10


def test_the_fixture_is_a_real_test_not_a_rubber_stamp() -> None:
    """Mutating an expectation must make the fixture fail."""
    tasks = evaluate.load_fixture(FIXTURE)
    broken = dict(tasks[-1])
    broken["expect"] = dict(broken["expect"], verified=not broken["expect"]["verified"])
    outcome = evaluate.run_task(broken)
    assert outcome.passed is False
    assert outcome.reasons


def test_check_fixture_reports_a_named_check() -> None:
    result = evaluate.check_fixture(FIXTURE)
    assert result.ok is True
    assert result.name == "loop.task_fixture"


def test_a_missing_fixture_is_an_error() -> None:
    with pytest.raises(evaluate.FixtureError):
        evaluate.load_fixture(FIXTURE.parent / "not-a-fixture.json")


def test_a_malformed_fixture_is_an_error(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text('{"version": 1, "tasks": [{"id": "x"}]}', encoding="utf-8")
    with pytest.raises(evaluate.FixtureError):
        evaluate.load_fixture(target)
