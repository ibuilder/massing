# Internal notes — not part of the published documentation

Everything under `docs/internal/` is a **working record**, not documentation. It is here so decisions
stay auditable, and it is deliberately fenced off from the published site.

`docs/` doubles as the GitHub Pages web root — `.github/workflows/pages.yml` copies it to `_site/`.
That is why this directory exists: without it, every internal audit and half-finished plan was served
as a page on massing.build, next to the user guide, with nothing to tell a visitor which was which.
The workflow now excludes `internal/`, and `apps/web/src/shell/docsPublished.test.ts` fails if a new
internal note lands somewhere Pages would publish it.

**If you are looking for how to use or run Massing, you are in the wrong folder.** Start at
[../README.md](../README.md).

## What is in here

### `archive/` — point-in-time audits, superseded
Each of these was true on the day it was written and has been overtaken by shipped work. They are kept
because the *reasoning* is worth more than the conclusion: several record why an approach was rejected,
which is the thing a future reader is most likely to re-propose.

The current state of any item below lives in [../roadmap.md](../roadmap.md),
[../roadmap-completed.md](../roadmap-completed.md) and [the changelog](../../CHANGELOG.md) — **not
here**. Do not cite an archived file as current.

| File | What it was | Superseded by |
| --- | --- | --- |
| `security-roadmap.md` | **LIVE, not superseded** — the standing security work queue: what is closed and the gate that proves it, what is open and who decides. Controls live in the [threat model](../security/threat-model.md); this is priority and ownership. | not superseded — active |
| `audit-2026-06.md` | Full-stack program audit (architecture, background work, relationships) | roadmap + changelog |
| `status.md` | Build-status snapshot at v0.3.86 — "verified vs pending" per milestone | roadmap + changelog. It also carried three numbers that had rotted: Node 20.3.1 (actually 24), 306 backend tests (441), and "since passed v0.3.614" (v0.3.796) |
| `phase2-large-models.md` | Build-order Phase 2 plan for large/federated models | Shipped: Fragments streaming + LayerManager |
| `production-readiness.md` | Security/perf/modularity/test/deploy pass with a prioritised backlog | Backlog absorbed into roadmap; see also [../security/threat-model.md](../security/threat-model.md) |
| `security-audit-2026-07.md` | Platform security audit, July 2026 | Findings fixed; posture lives in [../../SECURITY.md](../../SECURITY.md) |
| `gc-tools-audit.md` | Per-module audit of the 69 GC-portal modules | roadmap + [../gc-portal.md](../gc-portal.md) |
| `gc-modules-roadmap.md` | Field-vs-office deep dive across the config-driven GC modules | roadmap |
| `module-room-audit.md` | 133 registers against the seven rooms; sprints 1–2 built, 3–6 proposed | roadmap; the allocation itself is enforced by `test_module_rooms.py` |
| `module-plugin-system.md` | PLAN, 2026-07-30 — a WordPress/Joomla-style plugin system: rooms as directories, third-party module packs, and the decision that inverts R26 (the directory becomes authoritative for the room, because a third-party module must be reachable without editing a core table) | Nothing built. Sequencing + a cross-lane warning in §7 |
| `module-field-sweep.md` | Field-level sweep of all 133 modules, 2026-07-29 — fields, fieldsets, relationships, CRUD. Compares against a Django app the user built previously, which uses ForeignKeys where these modules used strings. Applied: 54 additive text+reference pairs, 67 units moved out of field names, 20 percent retypes, 41 widened tables, and two live fake-link defects in the reference renderer | Nothing — **current**. Every number in it is a floor in `test_module_fields.py`; §8 lists what is deliberately not done |
| `ux-findings.md` | App-wide heuristic UX review | Shipped through the R24 interface ring |
| `ux-ia.md` | Information-architecture plan for ~100 registers | Shipped as the room spine (`apps/web/src/shell/spine.ts`) |
| `design-audit.md` | External design audit, 2026-07-25 — 18 findings, 5 principles | R24 interface ring |
| `layout-parity.md` | Proof that the room spine lost nothing vs the old rail | Now enforced by `parity.test.ts` |

Two of these are worth calling out, because they are the pattern this repo keeps re-learning: the
guarantees in `layout-parity.md` and `ux-ia.md` only stopped rotting once they became **tests**
(`parity.test.ts`, `spine.test.ts`). A document asserting a property is a document that will disagree
with the product eventually. See the "Verify, don't recall" section of [../../CLAUDE.md](../../CLAUDE.md).

### `research/` — live research and plans for unbuilt things
Not superseded, not documentation either: these describe work that is planned, partially built, or
deliberately deferred. A reader should treat every claim here as a **proposal**.

| File | Status |
| --- | --- |
| `plugin-architecture-plan.md` | Plan only — nothing built. Free core + installable capability plugins. |
| `caching-research.md` | Research, 2026-07-27: our caches bound the wrong quantity. |
| `cost-db-import-plan.md` | Partially built. Vintage-versioned cost DB; referenced from `cost_db.py` and `models.py`. |
| `proforma-asset-class-scope.md` | Research, 2026-08-01: what six institutional CRE underwriting models require that our proforma cannot express. Scope + sequencing; items 1-2 shipped, 3-6 unbuilt. |
| `sibling-repo-import-2026-08-01.md` | Evaluation + outcome, 2026-08-01: what to import from the four sibling repos. **Executed** — the four phases shipped in v0.3.811, and the "Outcome" section records that three of them changed on contact (a premise check shrank one, a measurement moved a threshold 4x, and a Fragments-writer blocker rescoped another). Read the Outcome before the Plan. |
| `marketing-copy.md` | Messaging drafts. Reflects shipped capability only — check before reuse, copy rots faster than code. |

### Design records — current, 2026-08-09

Written at v0.3.913 during the R36 print-path investigation. All three are **current**; each states
its own grade and the date it was measured.

| File | Status |
| --- | --- |
| `adr-001-sheet-composition.md` | **Decision record, Proposed.** Two sheet composers exist and disagree about which view kinds are valid — the shipping one renders a *plan* when asked for an axonometric, because the `axon` branch sits in the wrapper rather than the shared `_view_for_spec`. Chooses backporting the branch over migrating the routes, and says what would reverse that. |
| `r36-viewer-subapp-design.md` | **Design pass + slice plan** for R36-VIEWER-SUBAPP. Its finding is that the roadmap entry's premise had gone stale: CANVAS-PEER already shipped the axonometric-as-a-drawing half, so the print slice is a dispatcher branch, not a rendering pipeline. Six slices, each shipping green alone. |
| `viewer-conformance-2026-08-13.md` | **LIVE** — MassingViewer's `RemoteKernel` run against a LIVE `:8093` with a real project (school_str.ifc, 8.6 MB, 500 elements queryable). **1 of the 7 endpoints it calls works as-is**: two absent (`spatial-tree`, `elements/properties`), three differing by path or scoping, and `/edit` taking `recipe` where the kernel sends `{op, params}` — the only item with real design content. Also corrects the roadmap's unfair claim that their suite was "a green check with no subject": their own header says it runs on cassettes and proves the adapter against the protocol as documented, not against our service. | not superseded — active |
| `org-integration-plan-2026-08-11.md` | **LIVE** — survey of all ten MassingCloud repos with a recommendation. All eight code repos verified MIT by reading the LICENSE file (the GitHub API reports NO-LICENSE for every one, including massingbill). Main finding: **massingcapture** is the one never-assessed repo and the only one matching the stated reality-capture gap; it declares `dependencies = []`. Sequenced as a PARTIAL vendor (probe → ingest → adapters), because unlike massingplan it is a whole application carrying a server and a bridge to a platform we rejected. | not superseded — active |
| `plan-2026-08-10.md` | **LIVE, not superseded** — plan state after v0.3.915-924: the frontend-framework question CLOSED (neither React nor Reflex; the CRUD third is the server-side candidate, measured at ~13k of ~47k hand-written lines), sibling-integration state per repo, the two decisions that are the user's (CC0 on the permitted list; massingviser vs modelmaker as the platform), and the next four items in order. | not superseded — active |
| `runway-claude-2026-08-19.md` | **LIVE** — handoff after **v0.3.1005**. Stack through #300 then cite-highlight. R31 closed. Next is capture-first home or a11y journeys. | not superseded — active |
| `vendorable-core-standard.md` | **LIVE, not superseded** — the adoption bar for MassingCloud libraries: a framework-free core with zero runtime deps, proven by an architecture test. Derived from three measured adoptions, and argues explicitly AGAINST standardising on one web framework — massingplan is Flask and vendored cleanly into our FastAPI service, while massingbill is blocked for reasons unrelated to Flask. `massingcapture` is the reference implementation. | not superseded — active |
| `dependency-advisories.md` | **LIVE, not superseded** — advisories carried knowingly in `requirements.lock`: only the ones with NO published fix, since anything fixable is blocked in CI by `scripts/audit_lock_gate.py`. One entry (diskcache / CVE-2025-69872) with its re-review date. Also records a mitigation that was claimed and then found not to be in evidence — no tracked deploy file sets a read-only root filesystem. | not superseded — active |
| `tech-debt-2026-08-09.md` | **Audit.** Eight scored items; the top three tie at P=24 (two dependency bumps carrying CVEs in the production lock, plus the composer defect). Its "Checked and NOT counted" section is the load-bearing half — two candidate findings were dropped after verification, including one I had already half-written up. |

## Adding to this directory

Two rules, both learned from failures recorded in the table above:

1. **Date it and state its grade in the first paragraph** — "audit", "plan", "research", "nothing built
   yet". A file that does not say what it is gets cited as if it were current. Every archived file
   above needed a "superseded" banner retro-fitted for exactly that reason.
2. **If the document asserts a property of the code, write the test too.** Prose cannot fail. Put the
   claim in a gate and link the gate from the document.
