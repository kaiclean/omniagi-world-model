# TOOLS.md — OmniAGI Tool Registry

> Master registry of tools available to OmniAGI. Tools are capabilities the master can invoke or delegate to specialist seats. Each tool has a spec under `tools/` (and optionally a script under `scripts/`).

## Registered tools

| ID | Tool | Spec | Status | Notes |
|----|------|------|--------|-------|
| `file_read` | Read any harness file | `tools/file_read.md` | active | Use `read_file` or `cat` equivalent |
| `file_write` | Write/overwrite harness file | `tools/file_write.md` | active | Verify by read-back |
| `file_patch` | Targeted edit | `tools/file_patch.md` | active | Prefer over overwrite when surgical |
| `shell` | Run a shell command | `tools/shell.md` | active | Check exit code; respect disk limits |
| `web_search` | Web lookup | `tools/web_search.md` | active | External facts / current state |
| `model_route` | Route request to engine seat | `tools/model_route.md` | active | See harnesses/TOP10_AGENTIC_MOE.md |
| `memory_update` | Update MEMORY.md + changelog | `tools/memory_update.md` | active | Follow MEMORY.md update rules |
| `tool_register` | Register a new tool (self-extension) | `tools/tool_register.md` | active | See workflows/tool-extension.md |
| `missing_tool_detector` | Detect a capability gap during work | `tools/missing_tool_detector.md` | active | Triggers tool-extension workflow |

| `summarize_url` | Summarize a URL | `tools/summarize_url.md` | active | Demo-added via self-extension |
## Extension contract
To add a tool:
1. Create `tools/<name>.md` describing its purpose, inputs, outputs, and how to invoke.
2. (optional) Add `scripts/<name>.py` if a script is needed.
3. Add a row to the table above.
4. Run the verification step from `workflows/tool-extension.md`.
5. Log in `memory/CHANGELOG.md`.

## Deprecation
Mark status `deprecated` in the table, move spec to `tools/archive/`, log in changelog. Never silently delete.