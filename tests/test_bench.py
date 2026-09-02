"""Benchmark/evaluation framework tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omniagi import bench, cli


def _write_suite(directory: Path, payload: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "suite.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_committed_routing_suite_passes(registry) -> None:
    suites = bench.run_all(registry=registry)
    assert suites, "expected at least the committed routing suite"
    assert all(s.ok for s in suites)
    routing = next(s for s in suites if s.name == "routing")
    assert routing.total == 8
    assert routing.accuracy == 1.0


def test_discover_finds_committed_suites() -> None:
    paths = bench.discover()
    assert any(p.name == "routing.json" for p in paths)


def test_run_file_reports_specialist_mismatch(tmp_path: Path, registry) -> None:
    path = _write_suite(
        tmp_path,
        {
            "name": "wrong",
            "kind": "routing",
            "cases": [
                {"id": "bad", "task": "implement the parser", "expect": {"specialist": "critic"}}
            ],
        },
    )
    suite = bench.run_file(path, registry)
    assert suite.ok is False
    assert suite.passed == 0
    assert any("specialist" in reason for reason in suite.results[0].reasons)


def test_seat_and_confidence_expectations(tmp_path: Path, registry) -> None:
    path = _write_suite(
        tmp_path,
        {
            "name": "seat",
            "kind": "routing",
            "cases": [
                {
                    "id": "coder",
                    "task": "debug and refactor the code",
                    "expect": {
                        "specialist": "coder",
                        "seat": "qwen3-coder-480b-a35b",
                        "min_confidence": 0.5,
                    },
                }
            ],
        },
    )
    suite = bench.run_file(path, registry)
    assert suite.ok is True
    assert suite.results[0].actual["specialist"] == "coder"


def test_max_confidence_flags_high_confidence(tmp_path: Path, registry) -> None:
    path = _write_suite(
        tmp_path,
        {
            "name": "conf",
            "kind": "routing",
            "cases": [
                {
                    "id": "toohigh",
                    "task": "implement the parser",
                    "expect": {"max_confidence": 0.1},
                }
            ],
        },
    )
    suite = bench.run_file(path, registry)
    assert suite.ok is False
    assert any("confidence" in reason for reason in suite.results[0].reasons)


def test_min_accuracy_allows_partial(tmp_path: Path, registry) -> None:
    path = _write_suite(
        tmp_path,
        {
            "name": "partial",
            "kind": "routing",
            "min_accuracy": 0.5,
            "cases": [
                {"id": "ok", "task": "implement the parser", "expect": {"specialist": "coder"}},
                {"id": "bad", "task": "implement the parser", "expect": {"specialist": "scout"}},
            ],
        },
    )
    suite = bench.run_file(path, registry)
    assert suite.accuracy == 0.5
    assert suite.ok is True


def test_unknown_kind_raises(tmp_path: Path) -> None:
    path = _write_suite(tmp_path, {"name": "x", "kind": "nope", "cases": [{"task": "t"}]})
    with pytest.raises(bench.BenchError):
        bench.load_suite(path)


def test_missing_cases_raise(tmp_path: Path) -> None:
    path = _write_suite(tmp_path, {"name": "x", "kind": "routing", "cases": []})
    with pytest.raises(bench.BenchError):
        bench.load_suite(path)


def test_duplicate_case_ids_raise(tmp_path: Path) -> None:
    path = _write_suite(
        tmp_path,
        {
            "name": "x",
            "kind": "routing",
            "cases": [
                {"id": "dup", "task": "a", "expect": {}},
                {"id": "dup", "task": "b", "expect": {}},
            ],
        },
    )
    with pytest.raises(bench.BenchError):
        bench.load_suite(path)


def test_case_without_task_raises(tmp_path: Path) -> None:
    path = _write_suite(
        tmp_path, {"name": "x", "kind": "routing", "cases": [{"id": "a", "expect": {}}]}
    )
    with pytest.raises(bench.BenchError):
        bench.load_suite(path)


def test_suite_result_to_dict_shape(registry) -> None:
    suite = bench.run_all(registry=registry)[0]
    payload = suite.to_dict()
    assert set(payload) >= {"name", "kind", "total", "passed", "accuracy", "ok", "cases"}


def test_format_report_handles_no_suites() -> None:
    text = bench.format_report([])
    assert "no benchmark suites" in text


def test_cli_bench_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["bench", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["name"] == "routing"
    assert payload[0]["ok"] is True


def test_cli_bench_malformed_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_suite(tmp_path, {"name": "x", "kind": "routing", "cases": []})
    code = cli.main(["bench", str(path)])
    assert code == 2
    assert "benchmark error" in capsys.readouterr().out
