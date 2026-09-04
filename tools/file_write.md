# Tool: file_write

Write or overwrite a harness file through the tool runtime, verified by
read-back.

## Inputs
- `path` (str, required): must resolve inside the harness root; `.git` is refused.
- `content` (str, required)
- `overwrite` (bool, default true)
- `create_parents` (bool, default false)

## Outputs
- `{path, bytes_written, sha256, verified}`

## How to invoke
- CLI: `omniagi tool run file_write --args '{"path": "memory/scratch/a.md", "content": "hi\n", "create_parents": true}'`
- Python: `from omniagi.tool_runtime import run_tool; run_tool("file_write", {...})`

## Dependencies
- none (standard library)

## Verification
- The bytes are read back off disk and compared to the intended content before
  the call reports success; a mismatch is an error, never a success with a
  warning. `verified: true` therefore means the file on disk is what was asked
  for.
