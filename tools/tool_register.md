# Tool: tool_register

Register a new tool via the self-extension protocol.

## Purpose
Add a capability to the harness in one command, so "prefer the smallest patch"
is achievable rather than aspirational.

## Inputs
- tool_id (str): lowercase_with_underscores
- purpose (str), name (str, optional), script (harness-relative path, optional)

## Outputs
- an `ExtensionReport` listing each protocol step and the verification result

## How to invoke
- CLI: `omniagi extend <tool_id> --purpose "<one line>"`
- Demo in a throwaway harness copy: `omniagi extend --demo`
- Python: `from omniagi.extend import extend_tool`

## Dependencies
- `registry/harness.json` must be writable

## Verification
Verification is not optional: the protocol re-reads the registry and the spec
from disk and confirms the generated `TOOLS.md` row exists. If that fails it
raises and **does not** write a changelog entry claiming success.
See `workflows/tool-extension.md`.
