# Workflow: Tool Extension (missing-tool self-add)

> Lets OmniAGI detect a capability gap and add a new tool to the harness on its own.

## Trigger
During any agent-loop iteration, if a needed capability is not in `TOOLS.md`, run this workflow.

## Steps
1. **Detect & name the gap.** State: "Missing tool: <name> — <one-line purpose>."
2. **Specify the tool.** Create `tools/<name>.md` with:
   - Purpose
   - Inputs (schema)
   - Outputs (schema)
   - How to invoke (CLI command, Hermes tool name, or function signature)
   - Dependencies (if any)
   - Verification command (how to prove it works)
3. **Implement (if needed).** Add `scripts/<name>.py` for scripted tools. Keep lean; respect disk limits.
4. **Register.** Add a row to the table in `TOOLS.md` with status `active`.
5. **Verify.** Dry-run the tool: execute its invocation with a trivial input and confirm expected output. Record exit code / read-back.
6. **Log.** Append to `memory/CHANGELOG.md`: date, tool name, one-line summary, verification result.
7. **Resume** the original agent-loop iteration that detected the gap.

## Constraints
- Never claim a tool works without running the verification command.
- Never add a tool that creates a second master agent.
- Keep tools composable and single-purpose.
- If the tool needs a new engine seat, update `harnesses/TOP10_AGENTIC_MOE.md` too.