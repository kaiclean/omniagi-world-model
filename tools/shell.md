# Tool: shell

Run an allowlisted command as an argument vector.

## Purpose
Execute builds, git operations and scripts without opening a shell-injection
surface. Threat model: `docs/threat-model.md`.

## Inputs
- argv (list[str]): the command. A bare string is **rejected** — accepting one
  would require shell interpolation.
- workdir (path, optional): must resolve inside the harness root.
- timeout (float, default 60, max 900): every invocation is bounded.
- allow (list[str], optional): extra allowlisted program names.

## Outputs
- `{argv, exit_code, stdout, stderr, timed_out, ok}`

## How to invoke
- Python: `from omniagi.shell import run; run(["git", "status", "--short"])`

## Guarantees
- No `shell=True`, ever — no metacharacter interpretation.
- Only programs in `DEFAULT_ALLOWLIST` (extendable via `OMNIAGI_SHELL_ALLOWLIST`).
- Working directory cannot escape the harness root.
- A timeout returns `exit_code=124` with `timed_out=True` rather than looking
  like a clean failure.

## Verification
- Check `exit_code == 0` for success; a non-allowlisted program raises
  `ShellError` before anything is executed.
