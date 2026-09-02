"""CLI and docgen tests.

Exit codes matter more than output here: CI reads them, and the whole point of
the rewrite is that a broken tool must not exit 0.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from omniagi import docgen
from omniagi.cli import main
from omniagi.results import Status

HEX64 = re.compile(r"^[0-9a-f]{64}$")


# -- exit codes ----------------------------------------------------------------


def test_check_passes_on_the_repository(temp_harness: Path, capsys) -> None:
    assert main(["check"]) == 0
    assert "RESULT: PASS" in capsys.readouterr().out


def test_check_fails_on_a_tampered_harness(temp_harness: Path) -> None:
    (temp_harness / "OmniAGI.md").write_text("tampered\n", encoding="utf-8")
    assert main(["check"]) == 1


def test_check_emits_machine_readable_json(temp_harness: Path, capsys) -> None:
    assert main(["check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "PASS"
    assert any(item["name"] == "constitution.single_master" for item in payload["checks"])


def test_check_does_not_dirty_the_tree(temp_harness: Path) -> None:
    before = {p: p.read_bytes() for p in temp_harness.rglob("*.md")}
    main(["check"])
    after = {p: p.read_bytes() for p in temp_harness.rglob("*.md")}
    assert before == after


def test_hash_prints_64_hex_characters(temp_harness: Path, capsys) -> None:
    assert main(["hash", "OmniAGI.md"]) == 0
    assert HEX64.match(capsys.readouterr().out.strip())


def test_hash_of_a_missing_file_exits_nonzero(temp_harness: Path, capsys) -> None:
    """The original bug: an error message printed with exit status 0."""
    assert main(["hash", "no-such-file.md"]) == 1
    captured = capsys.readouterr()
    assert captured.out.strip() == ""
    assert "error" in captured.err.lower()


def test_hash_without_arguments_is_a_usage_error(temp_harness: Path) -> None:
    assert main(["hash"]) == 2


def test_verify_manifest_exit_codes(temp_harness: Path) -> None:
    assert main(["hash", "--verify-manifest"]) == 0
    (temp_harness / "OmniAGI.md").write_text("tampered\n", encoding="utf-8")
    assert main(["hash", "--verify-manifest"]) == 1


def test_route_outputs_json_by_default(temp_harness: Path, capsys) -> None:
    assert main(["route", "write", "a", "python", "function"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["specialist"] == "coder"
    assert 0.0 <= payload["confidence"] <= 1.0


def test_route_explain_is_human_readable(temp_harness: Path, capsys) -> None:
    assert main(["route", "fix the failing test", "--explain"]) == 0
    out = capsys.readouterr().out
    assert "confidence" in out.lower()
    assert "seat" in out.lower()


def test_route_without_a_task_is_a_usage_error(temp_harness: Path) -> None:
    assert main(["route", "  "]) == 2


def test_extend_missing_tool_id_is_rejected(temp_harness: Path) -> None:
    assert main(["extend", "Bad-Id", "--purpose", "x"]) == 1


def test_memory_command_reports_status(temp_harness: Path, capsys) -> None:
    assert main(["memory"]) == 0
    assert "memory." in capsys.readouterr().out


def test_watch_once_returns_health_status(temp_harness: Path) -> None:
    assert main(["watch", "--once"]) == 0
    (temp_harness / "OmniAGI.md").write_text("tampered\n", encoding="utf-8")
    assert main(["watch", "--once"]) == 1


def test_seats_lists_every_registered_seat(temp_harness: Path, capsys, registry) -> None:
    assert main(["seats"]) == 0
    out = capsys.readouterr().out
    for seat in registry.seats:
        assert seat["id"] in out


def test_unknown_command_exits_nonzero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["definitely-not-a-command"])
    assert excinfo.value.code != 0


# -- docgen --------------------------------------------------------------------


def test_committed_docs_are_current() -> None:
    assert docgen.check_docs().status is Status.PASS


def test_generation_is_idempotent(temp_harness: Path) -> None:
    assert docgen.generate() == []


def test_stale_generated_block_is_detected(temp_harness: Path) -> None:
    target = temp_harness / "TOOLS.md"
    body = target.read_text(encoding="utf-8").replace("file_hasher", "file_hashr", 1)
    target.write_text(body, encoding="utf-8")

    assert "TOOLS.md" in docgen.generate(check_only=True)
    assert docgen.check_docs().status is Status.FAIL
    assert main(["docs", "--check"]) == 1


def test_regeneration_repairs_a_stale_block(temp_harness: Path) -> None:
    target = temp_harness / "TOOLS.md"
    target.write_text(
        target.read_text(encoding="utf-8").replace("file_hasher", "file_hashr", 1), encoding="utf-8"
    )
    assert "TOOLS.md" in docgen.generate()
    assert docgen.check_docs().status is Status.PASS


def test_prose_outside_the_markers_survives_regeneration(temp_harness: Path) -> None:
    target = temp_harness / "TOOLS.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nHand-written note.\n", encoding="utf-8")
    docgen.generate()
    assert "Hand-written note." in target.read_text(encoding="utf-8")


def test_missing_markers_are_an_error_not_a_silent_skip(temp_harness: Path) -> None:
    (temp_harness / "TOOLS.md").write_text("# Tools\n\nno markers here\n", encoding="utf-8")
    with pytest.raises(docgen.DocgenError):
        docgen.generate()


# -- installed entry point -----------------------------------------------------


def test_module_entry_point_works_as_a_subprocess(repo_root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "omniagi.cli", "check"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "RESULT: PASS" in completed.stdout
