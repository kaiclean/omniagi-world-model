"""Hardened shell tool.

Threat model in ``docs/threat-model.md``. Guarantees:

* **No shell interpolation.** Commands are argument vectors executed without
  ``shell=True``, so there is no metacharacter injection surface.
* **Allowlisted executables.** Only programs in :data:`DEFAULT_ALLOWLIST` (or an
  explicitly supplied allowlist) may run.
* **Bounded.** Every invocation has a timeout and captured output.
* **Contained.** The working directory must stay inside the harness root.
* **Honest.** A timeout or non-zero exit is returned as such; nothing is
  reported as success without an exit code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import harness_root

DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 900.0

#: Executables the harness is permitted to run. Deliberately small.
DEFAULT_ALLOWLIST = frozenset(
    {
        "git",
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "sha256sum",
        "shasum",
        "ls",
        "cat",
        "grep",
        "rg",
        "diff",
        "omniagi",
    }
)

ALLOWLIST_ENV_VAR = "OMNIAGI_SHELL_ALLOWLIST"


class ShellError(RuntimeError):
    """Raised when a command is rejected before execution."""


@dataclass(frozen=True)
class ShellResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "ok": self.ok,
        }


def effective_allowlist(extra: Sequence[str] | None = None) -> frozenset[str]:
    allowed = set(DEFAULT_ALLOWLIST)
    env_extra = os.environ.get(ALLOWLIST_ENV_VAR, "")
    allowed.update(item.strip() for item in env_extra.split(",") if item.strip())
    if extra:
        allowed.update(extra)
    return frozenset(allowed)


def _validate_workdir(workdir: Path | str | None) -> Path:
    root = harness_root()
    if workdir is None:
        return root
    target = Path(workdir)
    target = (root / target if not target.is_absolute() else target).resolve()
    if target != root and root not in target.parents:
        raise ShellError(f"workdir escapes the harness root: {workdir}")
    if not target.is_dir():
        raise ShellError(f"workdir does not exist: {workdir}")
    return target


def run(
    argv: Sequence[str],
    workdir: Path | str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    allow: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
) -> ShellResult:
    """Run an allowlisted command as an argument vector.

    ``argv`` must be a sequence; a bare string is rejected, because accepting
    one is how shell-injection bugs are born.
    """
    if isinstance(argv, str):
        raise ShellError(
            "pass the command as a list of arguments, not a string - "
            "string commands would require shell interpolation"
        )
    argv = [str(part) for part in argv]
    if not argv:
        raise ShellError("empty command")

    program = Path(argv[0]).name
    allowlist = effective_allowlist(allow)
    if program not in allowlist:
        raise ShellError(
            f"command '{program}' is not allowlisted; allowed: {', '.join(sorted(allowlist))}"
        )
    if shutil.which(argv[0]) is None and not Path(argv[0]).is_file():
        raise ShellError(f"command not found on PATH: {argv[0]}")

    if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise ShellError(f"timeout must be in (0, {MAX_TIMEOUT_SECONDS}]; got {timeout}")

    cwd = _validate_workdir(workdir)

    try:
        completed = subprocess.run(  # noqa: S603 - argv form, no shell, allowlisted
            argv,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return ShellResult(
            argv=argv,
            exit_code=124,
            stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
            stderr=f"timed out after {timeout}s",
            timed_out=True,
        )

    return ShellResult(
        argv=argv,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )
