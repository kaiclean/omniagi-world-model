# Tool: file_read

Read any harness file through the tool runtime.

## Inputs
- `path` (str, required): harness-relative or absolute; must resolve **inside**
  the harness root.
- `max_bytes` (int, default 100000, max 1000000): read cap.

## Outputs
- `{path, bytes, truncated, sha256, content}`

## How to invoke
- CLI: `omniagi tool run file_read --args '{"path": "LICENSE"}'`
- Python: `from omniagi.tool_runtime import run_tool; run_tool("file_read", {"path": "LICENSE"})`

## Dependencies
- none (standard library)

## Verification
- Returns `ok: true` with non-empty `content` and a sha256 of the whole file for
  an existing file; a missing file, a directory, or a path escaping the harness
  root returns `ok: false` with an error message. Never a silent empty string.
