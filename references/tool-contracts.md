# Tool Contracts (generated)

> Typed input/output contracts for every registered tool, generated from
> `registry/harness.json`. Do not edit by hand; run `omniagi docs` to refresh.

Each tool declares the arguments it accepts, the values it returns and the
errors it may raise. The orchestrator validates arguments against these
contracts before a tool runs, and `omniagi check` fails if an active tool ships
a malformed contract.

<!-- omniagi:generated:start id=tool-contracts -->
### `file_read`

Read a UTF-8 file inside the harness root.

_Inputs:_
- `path` (string, required) — Harness-relative path to read.

_Outputs:_
- `content` (string) — The file's decoded contents.

_Raises:_ path escapes the harness root; file does not exist.

### `file_write`

Atomically write a UTF-8 file inside the harness root.

_Inputs:_
- `path` (string, required) — Harness-relative path to write.
- `content` (string, required) — The full new contents of the file.

_Outputs:_
- `bytes_written` (integer) — Number of bytes written.

_Raises:_ path escapes the harness root.

### `file_patch`

Replace an exact, unique text span in a file.

_Inputs:_
- `path` (string, required) — Harness-relative path to edit.
- `old` (string, required) — Exact text to replace; must be unique in the file.
- `new` (string, required) — Replacement text.

_Outputs:_
- `replaced` (boolean) — Whether the replacement was applied.

_Raises:_ old text not found; old text is not unique; path escapes the harness root.

### `shell`

Run an allowlisted, trusted executable as an argument vector.

_Inputs:_
- `argv` (array, required) — Command as an argument vector; a bare string is refused.
- `timeout` (number, optional) — Seconds before the command is killed.

_Outputs:_
- `exit_code` (integer) — Process exit status (124 on timeout).
- `stdout` (string) — Captured standard output.
- `stderr` (string) — Captured standard error.
- `timed_out` (boolean) — Whether the command was killed on timeout.

_Raises:_ command is not allowlisted; command not found on PATH; executable is not inside a trusted directory; workdir escapes the harness root.

### `web_search`

Look up a query on the web (requires the network capability).

_Inputs:_
- `query` (string, required) — The search query.

_Outputs:_
- `results` (array) — Ranked result records.

_Raises:_ network access is unavailable.

### `model_route`

Choose a specialist and engine seat for a task.

_Inputs:_
- `task` (string, required) — Natural-language description of the task.

_Outputs:_
- `specialist` (string) — Selected specialist id.
- `seat` (string) — Selected engine-seat id.
- `confidence` (number) — Routing confidence in [0, 1].

### `memory_update`

Append a deduplicated, dated entry to the changelog.

_Inputs:_
- `message` (string, required) — The changelog message to append.

_Outputs:_
- `appended` (boolean) — Whether a new line was written.

### `tool_register`

Run the transactional self-extension protocol for a new tool.

_Inputs:_
- `tool_id` (string, required) — Lowercase snake_case id for the new tool.
- `name` (string, required) — Human-readable tool name.
- `purpose` (string, required) — What the tool does.
- `script` (string, optional) — Optional harness-relative implementation path.

_Outputs:_
- `verified` (boolean) — Whether the extension was verified by read-back.

_Raises:_ tool is already registered; declared script does not exist; verification failed.

### `missing_tool_detector`

Detect whether a needed capability lacks a registered tool.

_Inputs:_
- `capability` (string, required) — The capability being sought.

_Outputs:_
- `gap` (boolean) — Whether a capability gap exists.
- `suggestion` (string) — Suggested tool id to create, if any.

### `file_hasher`

Compute the SHA-256 of a harness file.

_Inputs:_
- `path` (string, required) — Harness-relative path to hash.

_Outputs:_
- `sha256` (string) — Lower-case hex digest.

_Raises:_ file does not exist; path escapes the harness root.

### `summarize_url`

Fetch and summarize a URL (requires the network capability).

_Inputs:_
- `url` (string, required) — An http or https URL.

_Outputs:_
- `summary` (string) — A short textual summary.

_Raises:_ network access is unavailable; url is not http or https.

### `seat_health`

Probe engine-seat availability without fabricating a verdict.

_Inputs:_
- `seat_id` (string, optional) — Seat to probe; omit to probe all.

_Outputs:_
- `available` (boolean) — Whether a usable seat was found.
- `reason` (string) — Evidence for the verdict.
<!-- omniagi:generated:end id=tool-contracts -->
