# Changelog

All notable changes to the **master-builder** skill.

## [0.3.2] — 2026-07-20
Fabrication-output honesty boundary.

### Added
- `construction-delivery.md` **Fabrication outputs — the honest boundary on machine formats** — a
  machine bending/cutting file (BVBS/BF2D, DSTV-NC, CAM) is a consequential, near-irreversible output;
  ship the human-read bending schedule (legs / angles / shape / mass) first, and hold the byte-exact
  machine format behind validation against the authoritative spec + a real importer. Mirrors the shipped
  rebar bending-detail schedule and its gated BVBS follow-up.

## [0.3.1] — 2026-07-20
Place-grounding mechanized in the Master Builder brief.

### Changed
- `global-codes.md` §8 **Grounding in place, mechanized** — documents how the brief resolves the code
  family from jurisdiction and derives hemisphere + climate band from the model's georeferenced
  coordinates, while emitting the hazard *parameters* to verify locally (never inventing load values).

## [0.3.0] — 2026-07-20
Co-evolution pass: the protocol became running software, and the doctrine gained the principle that made
it possible.

### Added
- `build-doctrine.md` §11 **Synthesis over sources of truth** — a whole-project meta-view (readiness
  brief, health scorecard, go/no-go) reads the signals the canonical engines already produce and composes
  them, guarded and grounded-in-place, never re-deriving code-check/estimate/clash inside the synthesis.

### Changed
- `digital-toolkit.md` §8 — documents the **Master Builder brief** now live in Massing
  (`GET /projects/{pid}/master-builder/brief`): the 8-step protocol run over a project's own data,
  grounded in its jurisdiction, per-step readiness + gap-closing links, with the honest-status boundary
  in the payload. The skill's protocol is now the reference for a shipped feature.

## [0.2.0] — 2026-07-20
Enrichment pass after grounding on real projects and a live feasibility test (a retail-to-vertical-farm
development thesis and its pro-forma model).

### Added
- `references/build-doctrine.md` — cross-cutting engineering lessons distilled from real platforms
  (source-of-truth & stable identity, do heavy work at the right layer, open interchange, staged-
  validation gate, hard rails on irreversible actions, honest status, compliance-as-code).
- `references/pro-forma-review.md` — forensic model/deal review: reframe the asset, reconciliation pass,
  a defect checklist (NOI gross-up, dropped cost lines, non-cash in OpEx, zero-vacancy, unit errors),
  the three-questions test for assumptions, cost-concentration analysis, and validate-demand-before-capital.

### Changed
- SKILL.md protocol now leads program analysis with "name what the asset actually is" (reframe first).
- `global-codes.md` — utility interconnection / will-serve added as a schedule-and-cost gate for
  energy- and water-intensive uses and on-site generation.
- `digital-toolkit.md` and `construction-delivery.md` corrected to the verified architecture of the
  real repos (Massing on That Open Fragments + IfcOpenShell with GUID-stable server-side edit recipes,
  three pillars Model/Construction/Finance, code-intelligence pre-checks; gcPanel/ConstructAI on Next.js/TS).

## [0.1.0] — 2026-07-20
Initial release.

### Added
- SKILL.md — the Master Builder Protocol, ground-in-place rule, professional boundaries, output conventions.
- References: `global-codes.md`, `development-lifecycle.md`, `real-estate-finance.md`,
  `construction-delivery.md`, `digital-toolkit.md`.
