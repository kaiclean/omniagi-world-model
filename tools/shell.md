# Tool: shell
Run a shell command (builds, git, network, scripts).
## Inputs
- command (str), optional workdir, timeout
## Outputs
- stdout/stderr, exit_code
## Invoke
- Hermes: `terminal(command=...)` (foreground) or `terminal(background=True)` for long runs
## Verify
- Check exit_code == 0 for success; inspect output for errors.
- Respect disk limits (host often <5GB free).
