# Architecture decision records (ADR-LITE)

One page per **load-bearing** decision — context, the decision, consequences. Nothing else.

## When to write one

A decision earns an ADR when reversing it later would be expensive and the *why* won't be obvious
from the code: a storage model, a contract shape, a dependency stance, a security posture. Routine
feature work does not get an ADR — the CHANGELOG and roadmap carry that history.

## Format

```markdown
# ADR-NNNN: <decision as a short imperative>

Date: YYYY-MM-DD · Status: accepted | superseded by ADR-MMMM

## Context
What forced a decision (2–5 sentences).

## Decision
What we chose, stated plainly.

## Consequences
What this buys us; what it costs us; what would trigger revisiting.
```

Number sequentially. Never rewrite an accepted ADR — supersede it with a new one. No retroactive
backfill of pre-adoption history: the CHANGELOG already records it.
