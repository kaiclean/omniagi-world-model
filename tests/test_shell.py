"""Shell tool tests.

The shell is the harness's most dangerous capability, so these tests assert the
*refusals* far more than the successes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from omniagi import shell


def test_argv_form_runs_and_captures_output(temp_harness: Path) -> None:
    result = shell.run([sys.executable, "-c", "print('hello')"], allow=[Path(sys.executable).name])
    assert result.ok
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False


def test_string_command_is_rejected() -> None:
    with pytest.raises(shell.ShellError) as excinfo:
        shell.run("echo hello; rm -rf /")  # type: ignore[arg-type]
    assert "list of arguments" in str(excinfo.value)


def test_metacharacters_are_inert_because_no_shell_is_used(temp_harness: Path) -> None:
    """`;` and `$(...)` are literal arguments, never interpreted."""
    payload = "safe; touch pwned.txt; $(touch pwned2.txt)"
    result = shell.run(["echo", payload], allow=["echo"])
    assert result.ok
    assert payload in result.stdout
    assert not (temp_harness / "pwned.txt").exists()
    assert not (temp_harness / "pwned2.txt").exists()


def test_command_outside_the_allowlist_is_refused() -> None:
    with pytest.raises(shell.ShellError) as excinfo:
        shell.run(["curl", "https://example.com"])
    assert "not allowlisted" in str(excinfo.value)


def test_empty_command_is_refused() -> None:
    with pytest.raises(shell.ShellError):
        shell.run([])


def test_allowlist_applies_to_the_basename_not_the_path() -> None:
    """An absolute path to a non-allowlisted binary must not slip through."""
    with pytest.raises(shell.ShellError) as excinfo:
        shell.run(["/usr/bin/curl", "https://example.com"])
    assert "not allowlisted" in str(excinfo.value)


def test_missing_binary_raises_rather_than_reporting_failure_as_output() -> None:
    with pytest.raises(shell.ShellError) as excinfo:
        shell.run(["git-definitely-not-a-real-subcommand"], allow=["git-definitely-not-a-real-subcommand"])
    assert "not found" in str(excinfo.value)


def test_env_var_can_extend_the_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(shell.ALLOWLIST_ENV_VAR, "curl, wget")
    assert {"curl", "wget"} <= shell.effective_allowlist()


def test_default_allowlist_excludes_shells_and_network_clients() -> None:
    forbidden = {"sh", "bash", "zsh", "curl", "wget", "ssh", "sudo", "rm", "eval"}
    assert not (forbidden & set(shell.DEFAULT_ALLOWLIST))


def test_timeout_is_enforced_and_reported(temp_harness: Path) -> None:
    result = shell.run(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout=0.5,
        allow=[Path(sys.executable).name],
    )
    assert result.timed_out is True
    assert result.ok is False
    assert result.exit_code == 124


@pytest.mark.parametrize("timeout", [0, -1, shell.MAX_TIMEOUT_SECONDS + 1])
def test_out_of_range_timeouts_are_refused(timeout: float) -> None:
    with pytest.raises(shell.ShellError):
        shell.run(["ls"], timeout=timeout)


def test_workdir_outside_the_root_is_refused(temp_harness: Path) -> None:
    with pytest.raises(shell.ShellError) as excinfo:
        shell.run(["ls"], workdir="/etc")
    assert "escapes the harness root" in str(excinfo.value)


def test_workdir_traversal_is_refused(temp_harness: Path) -> None:
    with pytest.raises(shell.ShellError):
        shell.run(["ls"], workdir="../../..")


def test_missing_workdir_is_refused(temp_harness: Path) -> None:
    with pytest.raises(shell.ShellError):
        shell.run(["ls"], workdir="no/such/dir")


def test_workdir_defaults_to_the_harness_root(temp_harness: Path) -> None:
    result = shell.run(["ls", "OmniAGI.md"])
    assert result.ok


def test_nonzero_exit_is_reported_not_raised(temp_harness: Path) -> None:
    """A failing command is data, not an exception - but it is never 'ok'."""
    result = shell.run(["ls", "definitely-not-here"])
    assert result.ok is False
    assert result.exit_code != 0
