# Tool: file_patch
Targeted find/replace edit in a harness file.
## Inputs
- path, old_string (unique), new_string
## Outputs
- unified diff of change
## Invoke
- Hermes: `patch(mode='replace', path=..., old_string=..., new_string=...)`
## Verify
- Read patched region back; confirm only intended change.
