# Tutorial: add a tool

Fifteen minutes, end to end. By the end you will have added a real tool, proven
it works, and had CI enforce that it keeps working.

## 0. Setup

```bash
python3 -m pip install -e ".[dev]"
omniagi check          # must print RESULT: PASS
```

## 1. See the protocol run before you use it

```bash
omniagi extend --demo
```

This executes the full missing-tool protocol inside a *temporary copy* of the
harness. Files are genuinely written and read back — it is not a simulation —
but your working tree is untouched. Confirm with `git status --short`.

## 2. Detect a real gap

Suppose you need to count lines in a harness file and there is no tool for it.
Confirm the gap rather than assuming it:

```bash
omniagi route "count the lines in a harness file" --explain
grep -c line_counter registry/harness.json     # 0 → the gap is real
```

## 3. Implement it

Create `omniagi/line_counter.py`:

```python
"""Count lines in a harness file."""

from __future__ import annotations

from omniagi.hashing import _resolve_inside_root   # reuses the traversal guard


class LineCountError(RuntimeError):
    """Raised when the file cannot be read."""


def count_lines(rel_path: str) -> int:
    target = _resolve_inside_root(rel_path)
    if not target.is_file():
        raise LineCountError(f"file not found: {rel_path}")
    return len(target.read_text(encoding="utf-8").splitlines())
```

Two things matter more than the logic:

* it **raises** on failure — returning `-1` or `"Error"` would violate the
  `no_simulated_success` rule and `omniagi check` would catch it; and
* it reuses the path-traversal guard instead of inventing a second one.

## 4. Register it

```bash
omniagi extend line_counter \
  --name "Count lines in a harness file" \
  --purpose "Report the line count of a harness file" \
  --script omniagi/line_counter.py
```

That one command performs all six protocol steps: detect, specify, implement,
register, verify by read-back, log. If verification fails it raises and
deliberately does **not** write a changelog entry claiming success.

## 5. Inspect what changed

```bash
git status --short
```

You will see:

| File | Why |
|---|---|
| `omniagi/line_counter.py` | your implementation |
| `tools/line_counter.md` | generated spec, ready for you to fill in |
| `registry/harness.json` | the canonical registration |
| `TOOLS.md`, `references/tools-registry.md` | **generated** — never edit by hand |
| `memory/CHANGELOG.md` | one deduplicated line |

Adding a capability is a one-command change because every derived table is
generated. That is what makes "prefer the smallest patch" achievable rather than
aspirational.

## 6. Finish the spec

Open `tools/line_counter.md` and replace the placeholder Inputs, Outputs and
Verification sections. The Verification section must describe evidence a human
could reproduce, not an intention.

## 7. Test it

Add `tests/test_line_counter.py`:

```python
import pytest

from omniagi.line_counter import LineCountError, count_lines


def test_counts_a_real_file():
    assert count_lines("OmniAGI.md") > 0


def test_missing_file_raises():
    with pytest.raises(LineCountError):
        count_lines("no-such-file.md")
```

The second test is the important one: it proves the tool fails loudly.

## 8. Verify everything

```bash
pytest
omniagi check
omniagi docs --check
git status --short     # must be clean apart from your intended changes
```

## 9. If you changed a constitution file

```bash
omniagi hash --write-manifest
```

## Deprecating a tool

Never delete silently. Set `"status": "deprecated"` in `registry/harness.json`,
move the spec to `tools/archive/`, run `omniagi docs`, and log the reason.
