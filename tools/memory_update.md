# Tool: memory_update
Update MEMORY.md and changelog durably.
## Inputs
- fact (str) or correction
## Outputs
- updated MEMORY.md, appended changelog line
## Invoke
- Read MEMORY.md → patch/append → read back → append `memory/CHANGELOG.md`
## Verify
- Read MEMORY.md back; confirm entry present and consistent.
