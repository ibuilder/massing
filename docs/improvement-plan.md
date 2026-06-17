# Product Improvement Plan — full-codebase audit (2026-06-17)

A review of performance, UX, and competitive position across the three pillars (BIM viewer,
GC portal, proforma), with a prioritized roadmap. Items marked ✅ are done in this pass.

## Audit summary (health)
- **Gates green:** Python 8/8, web 10/10 + tsc clean, production build clean.
- **Live app sweep (all 3 workspaces):** no console errors, no uncaught failures. New endpoints
  (`/proforma/monte-carlo`, `/projects/{pid}/me`) return 200 against the rebuilt container.
- **Two expected, already-handled non-200s** (caught, but they log in the console):
  - `GET /projects/{id}/model.frag → 404` when a project has no published tiles (viewer falls
    back to samples).
  - `GET /projects/{id}/drawings/storeys → 409` when a project has no source IFC.
  Both should become explicit empty-states (no failed request) — see UX P0.

## Performance
- ✅ **P0 — Proforma Monte Carlo was auto-running 1000 solves (~3s) on every debounced edit.**
  Now on-demand via a button (solve + 25-solve sensitivity still update live). (`1d46d97`)
- **P1 — Work-queue scans.** `modules.my_work` / `notifications` / `search_all` iterate all 68
  module tables (`select(t).all()` each) + call `available_actions` per row → O(modules×records).
  The email digest multiplies this by member count. Fix: one indexed pass (UNION or a denormalized
  "open work" view), and memoize `available_actions` per (module, state, party).
- **P2 — Tree load.** Viewer eagerly pulls `/elements?limit=5000`; virtualize / lazy-expand the
  spatial tree for very large models.
- **P2 — Portal list render.** The record table re-renders fully on filter; virtualize rows for
  large modules and debounce server-side filters.

## UX
- **P0 — Viewer empty-states.** Replace the caught 404/409 with explicit "No published model —
  Convert" / "No source IFC" states (also removes console noise).
- **P1 — Inline list editing** (Procore parity): edit status / assignee / key fields directly in
  the module list table without opening the record.
- **P1 — Loading/skeleton states** for portal lists, dashboard, and drawings (currently blank
  until data arrives).
- **P2 — RFI revisions** (Procore parity): revise a closed RFI with a tracked revision chain.
- **P2 — Responsive portal tables + keyboard-first navigation**; dark/light parity audit.

## Competitive gap analysis (vs Autodesk ACC, Procore, Revizto, Navisworks, Trimble Connect)
We match or lead on: open/IFC-native, offline viewer, in-browser authoring round-trip, the
68-module portal, and the development proforma (which the BIM incumbents lack). Gaps:
- **AI assist** — "Draft RFI from selection" (subject/question/impact) à la Procore's Draft RFI
  Agent; we already have selection→RFI, so add an LLM draft step.
- **Real-time collaboration** — presence + live issue/viewpoint sync (Revizto's core). We have
  SSE notifications; add presence and shared viewpoints.
- **Document management + version control** for non-model docs (specs/drawings/submittal
  attachments) with revision history.
- **Mobile / field capture** — on-site photo→BCF (the P2 Capacitor item).
- **2D sheet ↔ 3D linking** and sheet markup.
- **Reporting / analytics** — a report builder + exportable project reports.

## Roadmap (prioritized; each independently shippable)
- **P0 (now, safe, high value):** ✅ MC on-demand · ✅ inline list edit (assignee + status) ·
  viewer empty-states (deferred — the 404/409 are benign + already handled; not worth extra probes).
- **P1:** ✅ work-queue query optimization (SQL-filtered my_work + party_allowed hardening) ·
  ✅ AI Draft RFI (Claude when keyed, template fallback) · ✅ loading/skeleton states · RFI revisions.
- **P2:** real-time presence + shared viewpoints · document/version management · mobile field
  capture · report builder · list/tree virtualization.
- **P3 (external-gated):** SSO/OIDC (IdP) · Capacitor build (Android SDK/Xcode) · APS RVT→IFC
  (paid) · Bonsai desktop bridge (Blender).

## Executed
- `1d46d97` — proforma Monte Carlo made on-demand (perf/UX).
- `7958e85` — inline list editing of assignee + status in the portal (P0 UX, Procore parity).
- `fe56b9e` — SQL-filtered cross-module work queue + `party_allowed` hardening (P1 perf + a
  latent-crash fix).
- AI **Draft RFI** — `POST /projects/{pid}/ai/draft-rfi` (`ai.py`): Claude (`claude-opus-4-8`,
  structured output, low effort) when `ANTHROPIC_API_KEY` is set, deterministic template draft
  otherwise. Wired into "+ RFI from selection" (prefills subject + question). Closes the
  headline competitive gap (Procore Draft-RFI parity).

## Module relationships (data-model wiring)
Audited all 68 modules' relation graph and tied the necessary missing links (refs 31→44,
rollups 10→16):
- **Cost coding consistency** — `budget`/`sov`/`timesheet` `cost_code` made a *reference* to the
  `cost_code` module (matching `commitment`/`direct_cost`); `cost_code` now rolls up
  budget + committed + direct + labor hours per code.
- **Change order → contract** — `cor → subcontract`; `subcontract` rolls up linked CO value.
- **Contract → SOV** — `sov → prime_contract`; `prime_contract` rolls up SOV value.
- **Meetings → action items** — `action_item → meeting`; `meeting` rolls up the action count.
- **Engineering** — `rfi → drawing`, `submittal → drawing`.
- **Field** — `delivery → commitment (PO)`, `incident → daily_report`, `equipment_log → equipment_rate`.
- **Closeout** — `warranty → asset_register`, `commissioning → asset_register`; `asset_register`
  rolls up warranty count.
All config-driven (module.json) — the form picker, related panel, and rollups pick them up with
no engine/UI changes. Verified: `test_modules` asserts the meeting↞action, cor↠subcontract, and
rfi→drawing resolutions.

## Revisions (engine feature, P2 — Procore parity)
Built **generically in the engine** (not RFI-only), opt-in per module via `"revisable": true` —
matching how board/relations/rollups work. `POST /modules/{key}/{rid}/revise` copies the source,
mints a `<ref>.N` ref, re-opens the workflow, links via `data.revises`, and marks the source
`data.superseded_by` (metadata in the data JSON — no migration). `get_record` exposes the
`revision` chain (number + prior/next briefs); the catalog advertises `revisable`. Enabled on the
document-type modules that are genuinely reissued: **rfi, submittal, drawing, transmittal, cor,
proposal, change_event, design_review** — off for logs/daily/timesheet/inspection/cost entries.
Web: a "⎘ Revise" button + revision-chain links in the record detail. Verified: `test_modules`
asserts RFI-001→RFI-001.1→.2, supersede-block (409), non-revisable reject (400), catalog flag.

## Report builder (P2) — done
`GET /projects/{pid}/report.pdf` (`report.py`) renders a one-document **project status report**
(KPIs, cost snapshot, open items by module, ball-in-court) from the live dashboard aggregation,
with reportlab + pagination. A "↓ Status report (PDF)" button sits on the construction dashboard.
Verified: `test_dashboard` asserts a valid `%PDF-` response.

## Real-time presence + shared viewpoints (P2) — done
`presence.py` (in-memory heartbeat store, per-process) + `POST/GET /projects/{pid}/presence`:
clients heartbeat every 20s (optionally sharing their camera viewpoint), peers read the live
roster. Viewer shows a "👥 N" indicator (click → jump to a peer's shared view) and a "⤴ Share
view" button. Verified: `test_presence` (roster, shared viewpoint, self-exclude, TTL prune).
_Note: per-process — back with Redis for multi-worker._

## Next up
The P2 program: document/version management, mobile field capture, list/tree virtualization.
