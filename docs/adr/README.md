# ADR log

Constitutional rules are cheap to write and expensive to live with. A rule
whose reason has been forgotten cannot be safely amended, so it either ossifies
or gets deleted by someone who never knew what it protected.

Every change to a non-negotiable, to the single-master model, or to an
enforcement mechanism requires an ADR here. Record the *forces*, not just the
decision.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-single-master-authority.md) | Single-master authority | Accepted |
| [0002](0002-registry-as-single-source-of-truth.md) | Registry as single source of truth | Accepted |
| [0003](0003-tools-fail-loudly.md) | Tools fail loudly | Accepted |
| [0004](0004-typed-tool-contracts-and-capability-approvals.md) | Typed tool contracts and capability approvals | Accepted |
| [0005](0005-tamper-evident-run-traces.md) | Tamper-evident run traces | Accepted |
| [0006](0006-bounded-checkpointed-autonomous-runs.md) | Bounded, checkpointed autonomous runs | Accepted |
| [0007](0007-typed-world-state-memory-with-provenance.md) | Typed world-state memory with provenance | Accepted |

## Template

```markdown
# ADR NNNN: Title

- Status: Proposed | Accepted | Superseded by ADR-NNNN
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
## Enforcement
```
