"""Hardened shell tool.

Threat model in ``docs/threat-model.md``. Guarantees:

* **No shell interpolation.** Commands are argument vectors executed without
  ``shell=True``, so there is no metacharacter injection surface.
* **Allowlisted executables.** Only programs in :data:`DEFAULT_ALLOWLIST` (or an
  explicitly supplied allowlist) may run.
* **Trusted executables.** The program name is resolved to a concrete absolute
  path and, in strict mode, that path must live inside a trusted directory so a
  hijacked ``PATH`` cannot substitute an attacker's binary for an allowlisted
  name.
* **Bounded.** Every invocation has a timeout and captured output.
* **Contained.** The working directory must stay inside the harness root.
* **Honest.** A timeout or non-zero exit is returned as such; nothing is
  reported as success without an exit code.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
TRUSTED_DIRS_ENV_VAR = "OMNIAGI_SHELL_TRUSTED_DIRS"

#: Directories whose executables are trusted by default. The interpreter's own
#: ``bin`` directory is added at runtime so virtualenv and CI tool-cache Pythons
#: (and the console scripts beside them) are trusted without configuration.
_SYSTEM_TRUSTED_DIRS = (
    "/usr/bin",
    "/bin",
    "/usr/local/bin",
    "/usr/sbin",
    "/sbin",
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
)


class ShellError(RuntimeError):
    """Raised when a command is rejected before execution."""


@dataclass(frozen=True)
class ShellResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    executable: str | None = None
    trusted: bool = False

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
            "executable": self.executable,
            "trusted": self.trusted,
        }


def effective_allowlist(extra: Sequence[str] | None = None) -> frozenset[str]:
    allowed = set(DEFAULT_ALLOWLIST)
    env_extra = os.environ.get(ALLOWLIST_ENV_VAR, "")
    allowed.update(item.strip() for item in env_extra.split(",") if item.strip())
    if extra:
        allowed.update(extra)
    return frozenset(allowed)


def trusted_dirs() -> tuple[Path, ...]:
    """Resolved directories whose executables are trusted."""
    dirs: set[Path] = set()
    for candidate in _SYSTEM_TRUSTED_DIRS:
        path = Path(candidate)
        if path.is_dir():
            dirs.add(path.resolve())
    # The interpreter's bin dir covers venvs and CI tool caches, plus the
    # console scripts (pytest, ruff, mypy, omniagi) installed alongside it.
    dirs.add(Path(sys.executable).resolve().parent)
    env_extra = os.environ.get(TRUSTED_DIRS_ENV_VAR, "")
    for item in env_extra.split(os.pathsep):
        item = item.strip()
        if item:
            resolved = Path(item).expanduser()
            if resolved.is_dir():
                dirs.add(resolved.resolve())
    return tuple(sorted(dirs))


def resolve_executable(program: str) -> Path | None:
    """Resolve ``program`` to a concrete absolute path, or ``None`` if absent."""
    found = shutil.which(program)
    if found is not None:
        return Path(found).resolve()
    candidate = Path(program)
    if candidate.is_file():
        return candidate.resolve()
    return None


def is_trusted(executable: Path, dirs: Sequence[Path] | None = None) -> bool:
    """Whether ``executable`` lives directly inside a trusted directory."""
    allowed = tuple(dirs) if dirs is not None else trusted_dirs()
    return executable.resolve().parent in allowed


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
    require_trusted: bool | None = None,
) -> ShellResult:
    """Run an allowlisted command as an argument vector.

    ``argv`` must be a sequence; a bare string is rejected, because accepting
    one is how shell-injection bugs are born.

    ``require_trusted`` controls executable-trust enforcement. When ``None``
    (the default) strict enforcement is enabled iff :data:`TRUSTED_DIRS_ENV_VAR`
    is set; otherwise the resolved path and its trust status are still recorded
    on the result but an untrusted path is not refused. Pass ``True`` to require
    a trusted executable regardless of the environment.
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

    executable = resolve_executable(argv[0])
    if executable is None:
        raise ShellError(f"command not found on PATH: {argv[0]}")

    if require_trusted is None:
        enforce = os.environ.get(TRUSTED_DIRS_ENV_VAR) is not None
    else:
        enforce = require_trusted
    trusted = is_trusted(executable)
    if enforce and not trusted:
        raise ShellError(
            f"executable '{executable}' is not inside a trusted directory; "
            f"trusted: {', '.join(str(d) for d in trusted_dirs())}"
        )

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
            executable=str(executable),
            trusted=trusted,
        )

    return ShellResult(
        argv=argv,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        executable=str(executable),
        trusted=trusted,
    )
