# Tool: tool_register
Register a newly created tool into TOOLS.md.
## Inputs
- id, name, spec path, status, notes
## Outputs
- new row in TOOLS.md table
## Invoke
- patch TOOLS.md table with new row
## Verify
- Read TOOLS.md back; grep for new tool id.
