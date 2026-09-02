# Workflow: Agent Loop

> Core execution loop for OmniAGI and all specialist subroutines.

## Loop
Repeat until the goal is satisfied or a true unrecoverable blocker is confirmed.

### 1. Understand
- Read current file state, errors, and relevant harness context (MEMORY.md, TOOLS.md, engine seats).
- State the exact sub-goal for this iteration in one sentence.

### 2. Plan
- Choose the next smallest action that produces observable progress.
- Define expected output and acceptance check before executing.
- Identify rollback if it fails.
- Pick engine seat via `tools/model_route.md` if a model call is needed.

### 3. Execute
- Run exactly one action (read/write/patch/shell/model call).
- Do not batch multiple mutating steps when verification depends on order.

### 4. Verify
- File written? Read it back or checksum/diff.
- Command run? Check exit code and output.
- Model called? Inspect returned content against expected schema.
- If pass → record step complete.
- If fail → go to 5.

### 5. Diagnose → Fix → Re-verify
- Capture exact error/context.
- Hypothesize cause.
- **If error indicates missing tool/capability → Invoke `workflows/tool-extension.md` to self-extend.**
- Apply smallest targeted fix (or use newly extended tool).
- Re-run the check.
- If still failing after 3 iterations (and self-extension failed/wasn't applicable), report a blocker with full context and stop.

### 6. (Optional) Self-extend
- If a capability gap was found, invoke `workflows/tool-extension.md` before continuing.

## Exit
- Goal met + every step verified with real evidence.
- Emit final verification report (see `OmniAGI.md` success definition).