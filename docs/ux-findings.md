# UX / UI findings — app-wide heuristic review

A lightweight pass across the four workspaces (Model / Drawings / Construction / Finance) and the
shared chrome, capturing issues by severity with a recommended order. Seeded from the 2026-06
tools-panel redesign; the rest is a backlog to work through, not yet implemented.

Severity: **High** (hurts daily use / blocks discovery) · **Med** (friction) · **Low** (polish).

## Done — tools & analysis surface (2026-06)
- ✅ **Two confusing tool surfaces.** Rule established: the floating viewer toolbar = *interact with
  the model*; the ⚙ Tools rail = *produce outputs / run analysis / batch edits*. Removed the
  duplicate rail "Measure" section (moved "clear" to the toolbar).
- ✅ **Everything always shown.** Tools rail is now a collapsible accordion with per-section
  preconditions; unmet → one muted "needs a project / source IFC" line + auto-collapse (no more
  repeated dead rows). Open/closed state persists.
- ✅ **Cramped results.** Cost / Energy / MEP / IDS / clash now open a readable result modal
  (`ui/result.ts`) with tables/metric grids; a one-line status stays in the rail.
- ✅ **Not role-aware.** Tools panel now persona-ordered (`TOOLS_BY_PERSONA`): a persona's primary
  tools sit on top, the rest fold under "More tools". Mirrors the existing workspace/rail filtering.
- ✅ **Construction portal scaled poorly (68 modules).** The catalog is now a collapsible,
  persona-aware section accordion (12 groups with count badges; `SECTIONS_BY_PERSONA` controls
  default-open), with ★ favorites pinned to a top group and a "Filter modules…" box that narrows and
  auto-expands matches. Open state persists; re-orders live on persona change.
- ✅ **Workspace ↔ tool overlap.** The ⚙ Tools rail now opens with a one-line note framing it as
  "model-derived analysis & exports", and the Cost section deep-links to the Construction workspace
  (where budgets/change-orders are managed) via an `aec:workspace` event — so the rail reads as a
  quick model-side surface, not a competing home.
- ✅ **Icon-only floating toolbar.** The ~20-glyph row is split into functional groups with
  separators — measure/visibility ┊ collaboration ┊ view-aids ┊ authoring (the authoring group and
  its divider hide for non-editors).

## Backlog

### Done (later pass)
- ✅ **Empty-state consistency.** Shared `.empty-state` style (one muted line + optional hint),
  applied to the portal (was unstyled), no-records/no-matches, drawings register, model-federation
  list, and Procore schedules.
- ✅ **Theme/contrast audit (light mode).** Verified the Tools accordion, result modal, catalog, and
  empty-states in light mode — all CSS-variable driven, good contrast, no fixes needed.
- ✅ **Keyboard & a11y (modal + accordions).** Result modal is `role="dialog"` + `aria-modal`, moves
  focus in on open, **traps Tab**, and **returns focus** to the opener on close; both accordions set
  `aria-expanded` and toggle it. (Minor remaining: the catalog ★ favorite is a span-in-button —
  click works, keyboard focus doesn't, without invalid nested-interactive markup.)

- ✅ **Result/feedback reuse.** Bulk actions (assign/transition/delete) now `toast` the result count
  and only reload on a real change (cancelling a prompt no longer reloads); sync/push/schedules
  already used toasts.

### Low (remaining)
- **Responsive / mobile** layout (rail + floating toolbar) — pairs with the Capacitor/Tauri-mobile
  wrapper (environment-gated).
- **Catalog ★ favorite keyboard focus** — currently a span-in-button; needs a non-nested-interactive
  restructure to be Tab-focusable.
- **Responsive / mobile** layout was not reviewed; the rail + floating toolbar likely need a
  narrow-viewport treatment.

## Finance / Proforma — revamp ✅ (2026-06, first pass shipped)
Shipped: the Finance view is now organized into **sub-tabs** (Feasibility · Budget & Capital ·
Underwriting · Deliverables) with a **sticky returns bar** (IRR / EM / yield-on-cost / NPV) that
re-solves live and shows an **underwriting guardrail badge** (U5). Investor memo + pitch deck moved
to the Deliverables tab. *Remaining (below): persona-gate the sub-tabs, visible inputs→proforma
flow, a Finance landing/deal-summary.*

## Finance / Proforma — revamp analysis (2026-06) ★
The Finance view grew from a proforma form into **11 stacked panels** in a single scroll
(drivers form · 🏗️ generate-from-zoning · 📐 Test Fit · 🏢 property · 🧱 budget · 🏦 Sources & Uses ·
⚡ specialty · 📐 model-link · sensitivity · Monte Carlo · draws). It works but no longer scales —
needs information architecture. Findings, by severity:

- **High — no IA / everything in one scroll.** Feasibility, capital, underwriting, and deliverables
  are interleaved with no grouping; the **returns (the whole point) are buried** mid-page and scroll
  away. *Fix:* reorganize the Finance workspace into sub-tabs (the `#fin-tabs` bar already exists with
  Proforma/Portfolio — extend it):
  - **Feasibility** — generate-from-zoning · Test Fit (compare/optimize) · property & tax.
  - **Budget & Capital** — cost budget · Sources & Uses · specialty assets.
  - **Underwriting** — deal-driver form · sensitivity · Monte Carlo · actuals/draws.
  - **Deliverables** — investment memo · pitch deck · model-link.
- **High — no persistent returns summary.** IRR / EM / yield-on-cost / NPV render inline and scroll
  off. *Fix:* a **sticky returns bar** (top of the Finance view) that re-solves live, always visible.
- **Med — implicit data flow.** Budget→cost-lines, specialty→ops, property→opex all have separate
  "Apply to proforma" buttons; the dependency isn't visible. *Fix:* one "inputs → proforma" status
  line (or auto-apply with an undo) so the user sees what feeds the deal.
- **Med — underwriting credibility cues missing** (ties to roadmap **U5**): no flag when IRR/YoC/cap
  fall outside market bands. *Fix:* surface guardrail badges on the returns bar.
- **Low — panel visual sameness.** Every panel is a dashed-border box; sub-tabs + section headers
  would give scan­nable hierarchy.

Broader app (post-feature-growth): the **persona system** should gate Finance sub-tabs too (a GC
rarely needs Monte Carlo); and a short **Finance landing/deal-summary** (key metrics + "what's next")
would orient new users — pairs with the onboarding tour.

## Not yet reviewed
- **Drawings set** workspace beyond the earlier layout fix — the sheet register / markup flow looks
  solid but deserves a task-flow review (create → markup → promote-to-RFI).
