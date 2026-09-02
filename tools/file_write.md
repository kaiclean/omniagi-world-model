# Tool: file_write
Write/overwrite a harness file completely.
## Inputs
- path (str), content (str)
## Outputs
- bytes written, verified hash/path
## Invoke
- Hermes: `write_file(path=..., content=...)`
## Verify
- Read file back after write and diff against intended content.
