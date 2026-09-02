# Constitution reference

The OmniAGI constitution has exactly one authoritative location:
**`WORLD_AGENTS.md`** in the harness root.

This file used to be a hand-maintained mirror of it. That was a bug, not a
convenience: it drifted from the original, and because it repeated the master
declaration verbatim it also created a second document asserting harness-wide
ownership. The `constitution.single_master` check now rejects any file outside
the constitution that makes those declarations.

If you want the constitution, read `WORLD_AGENTS.md`. If you want the
machine-readable form of who exists and what they may do, read
`registry/harness.json`.
