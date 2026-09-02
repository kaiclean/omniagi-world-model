# ADR 0003: Tools fail loudly

- Status: Accepted
- Date: 2026-09-02

## Context

The original `file_hasher` printed `Error: File not found` and exited `0`. CI
had a step named "verify file_hasher" that ran the command and checked the exit
code. Had CI ever run, it would have reported a green check for a completely
broken tool.

This is the worst possible failure mode for an autonomous system. A tool that
errors visibly costs one retry. A tool that reports success it did not achieve
corrupts every decision downstream of it, and the corruption is undetectable
from inside the loop — the agent has no way to know its evidence is fabricated.

The constitution already forbade simulating tool success. It was unenforceable
prose, and the very first tool in the repository violated it.

## Decision

Failure is always an exception, never a return value.

* `hash_file` raises `HashError`; there is no sentinel string or `None` path.
* No engine seat reachable → `SeatUnavailable`, never placeholder text.
* Self-extension verifies by reading its work back and raises on mismatch —
  and deliberately writes **no** changelog entry when verification fails, so
  the log never records a success that did not happen.
* Assertions on output are on *content*, not exit status: CI asserts the hasher
  emits 64 hexadecimal characters.

`constitution.check_no_simulated_success` executes the failure path and scans
the package for error-sentinel return patterns.

## Consequences

Callers must handle exceptions. This is the point: it makes the failure path
explicit at every call site instead of letting an error string flow onward as
if it were data.

The source scan is a heuristic and could flag legitimate code returning a string
that begins with `Error`. Such a return is almost always the bug this ADR
exists to prevent, so the false-positive rate is an acceptable price.

## Enforcement

`constitution.check_no_simulated_success`; `hashing.HashError`;
`adapters.SeatUnavailable`; `tests/test_hashing.py`; the hasher assertion step
in `.github/workflows/ci.yml`.
