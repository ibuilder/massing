# ADR-0001: Adopt lightweight architecture decision records

Date: 2026-07-24 · Status: accepted

## Context

The platform ships many releases per day directly to main. Load-bearing decisions (storage shapes,
contract designs, dependency stances) live in CHANGELOG entries and roadmap notes, which record *what*
shipped but scatter the *why* across hundreds of entries. An external strategy review (R18) flagged
the absence of a durable decision log as an enterprise-readiness gap.

## Decision

Adopt ADR-LITE: one page per load-bearing decision in `docs/adr/`, using the format in
[README.md](README.md). Future decisions only — no retroactive backfill, because the CHANGELOG and
roadmap already carry the history and a backfill would be reconstruction, not record.

## Consequences

Buys us: a single place a new engineer (or auditor) reads to understand why the platform is shaped the
way it is. Costs us: one page of writing per major decision. Revisit if the practice decays into
ceremony — an ADR nobody reads for a decision nobody questioned should not have been written.
