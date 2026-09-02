# Tool: file_read
Read any harness file.
## Inputs
- path (str): absolute or harness-relative path
## Outputs
- content + line numbers
## Invoke
- Hermes: `read_file(path=...)`
- Shell: `cat <path>` (prefer read_file)
## Verify
- Returns non-empty content for an existing file.
