# ADR 0004: This repository is a harness, not a world model

- Status: Accepted
- Date: 2026-09-04

## Context

The repository is called `omniagi-world-model` and the README opened with
"agent world model". Nothing here predicts anything. There is no state
transition function, no learned or hand-written dynamics model, no rollout of
"if the agent does X, the world becomes Y". What actually exists is a harness:
a registry, a router, a tool runtime, verification checks and a closed loop.

Calling that a world model costs credibility in the only place it matters —
someone reading the code after reading the claim — and it invites the project
to keep writing documents about prediction instead of writing a predictor.

## Decision

The artefact in this repository is **the OmniAGI harness**. The name
`omniagi-harness` is the accurate one; the repository slug stays where it is
until the owner renames it on GitHub (renaming a remote is not something the
code can do for itself, and a rename breaks existing clones and links).

Concretely:

* README, package description and architecture docs describe a harness.
* "World model" is reserved for a component that predicts the next state of an
  environment. If such a predictor is written, it gets its own module, its own
  fixture and its own evaluation — and only then does the phrase come back.
* `WORLD_AGENTS.md` keeps its filename: it is constitutionally pinned because
  `AGENTS.md` is a protected name, and renaming it is a separate, riskier
  change than fixing prose.

## Consequences

The repository slug and the artefact name disagree until a GitHub rename
happens. That is visible and explainable, which is strictly better than prose
that overclaims. Anyone landing here from the slug reads, in the first
paragraph, exactly what this is and what it is not.

## Enforcement

`constitution.check_*` cannot police adjectives. What is enforced instead is
that every capability claim in the README maps to a command that runs:
`omniagi check`, `omniagi tool run`, `omniagi loop`, `omniagi eval`. A claim
without a command is the thing to delete.
