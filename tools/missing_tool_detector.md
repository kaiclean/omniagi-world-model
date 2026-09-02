# Tool: missing_tool_detector
Detect a capability gap during agent-loop work.
## Inputs
- needed_capability (str), current TOOLS.md
## Outputs
- gap report: capability not found in TOOLS.md
## Invoke
- Read TOOLS.md; search for capability; if absent → trigger workflows/tool-extension.md
## Verify
- Negative search is confirmed (no matching row in TOOLS.md).
