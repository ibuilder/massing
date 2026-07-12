# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.214**.

> **The product feature roadmap, the code-quality/hardening initiative, AND the Wave 8 field-research
> upgrades are all effectively cleared.** Every headline feature theme shipped (generative design + Test
> Fit, developer/finance portal, full acquisition→turnover lifecycle, openBIM standards, AI-over-model,
> discipline spine, operations/resilience, scan-to-BIM + 2D→BIM); the four-domain hardening audit shipped
> as Waves 1–7 (observability, perf/scale, type boundary, modularization, reproducibility/ops, strictness
> + Docker); and **Wave 8** (2026 field scan) shipped **all seven tracks** — clash-coordination
> intelligence, model→field layout, load takedown, model hygiene, the CEP generator, Gaussian-splat
> reality capture, schedule-linked verified-as-built progress (v0.3.203–210), and ⑦'s origination-side
> **syndication connector** (v0.3.213). Since then: the **IFC5/IFCX data write-path** (v0.3.213) and an
> **in-browser E57 reader** (v0.3.214) closed the last two upstream-tagged items at the data layer. **The
> complete, re-ranked list of everything still open — swept up from every archive/parking-lot section — is
> the single "What's left" section below.** Everything under "Shipped archive" is historical reference only.

---

> **Shipped work lives in [roadmap-completed.md](roadmap-completed.md)** — the full done-archive (every wave, track, and release, A–D + L parking-lots, lifecycle/standards/discipline-spine/
> resourcing). This file now holds only the banner above and the open backlog below, so *what's left* is never buried under *what's done*.

## ⏳ What's left — the whole open roadmap, prioritized

**Everything not shipped, consolidated in one place — this is the single, authoritative backlog.** Every
historically-deferred item from every archive/parking-lot section in
[roadmap-completed.md](roadmap-completed.md) (A Test Fit · U underwriting · R built-world · M
materials/rendering · L interop · D platform, plus each "*Next:*" sub-note) has been swept up and re-ranked
here, so you never have to read the archive to know what's open. The product features, the
code-quality/hardening initiative (Waves 1–7), and Wave 8 (all seven tracks — ⑦'s connector shipped
v0.3.213) are done. Everything remaining is **incremental depth, spikes, upstream-blocked work, or
documented non-goals — nothing is blocking.** Ordered most-actionable first; pull an item up on real
customer need. Each line ends with its archive source in parentheses for the full original spec.

**① Generative-design & analysis depth — buildable now, pull up on customer need** *(the deepest, highest-value bucket)*
- **Test Fit yield optimization** *(§A)* — ✅ **DONE (v0.3.215)**: daylight-limited plate depth is now an
  **optimize dimension** (`optimize(depths=…)` / `targets.sweep_depth`) returning a `depth_curve` +
  `best_depth_m`, and a new **`core_efficiency`** metric scores the daylight-dark core; a "sweep plate
  depth" toggle charts it in the Test Fit panel. *Remainder:* **true polygon-offset footprint** with
  parking + drive-aisle placement on the real parcel (A6 shipped shoelace area; the offset/placement is next).
- **Structural generative depth** *(§R3/§A)* — **per-floor column taper** and **lateral-core geometry**
  in the generated frame (the advisor picks the system + rough sizing today; this makes the geometry
  follow the load path floor-by-floor).
- **Underwriting realism, deeper** *(§U)* — validate the **exit cap against the Comparables** record; a
  **full specialty P&L + ramp** (farm/energy business modelled over time, reporting blended vs
  real-estate-only IRR); wire **Monte-Carlo** sensitivity to the specialty risk discount.
- **Lean / takt production analytics** *(§R2/§R4)* — a **takt line-of-balance chart** in the UI tied to
  **daily-report actuals**; surface **PPC on the dashboard**; **production-rate actual-vs-takt** tracking.
- **Rendering & computational depth** *(§M)* — a **material editor + per-project palette** (edit the M1
  IfcMaterial/SurfaceStyle assignments); a **module-relations graph view** (reuse the Studio node canvas);
  heavier: real-time GI / baked AO / exterior HDRI skies.
- **Developer deliverable** *(§B6)* — a **pitch-deck variant** of the investment memo (10–20 slides, market
  + timeline sections, photos) alongside the existing memo/deck PDFs.

**② UX / performance / productivity (Part C — approve item-by-item)**
- **Role landing dashboards** — extend the Design-home command-center pattern to the **Finance and
  Developer** personas (Design home shipped; the other two are the remainder). *Highest-value UX item.*
- **Nav density** — per-stage collapse memory + a denser dashboard summary for the multi-card panels.
- **A11y** — keep verifying new tabs/dashboards (roles, focus order, contrast) as workspaces grow.
- *(⌘K, saved-views-per-role, cross-workspace deep-links both directions, and the `portal.ts` per-domain
  split all shipped — see §Part C archive.)*

**③ Interop / library evaluations — contained spikes, adopt only if it serves the mission** *(§L)*
- **L1 — `@ifc-lite/geometry` server-side converter spike** (MPL-2.0, claims ~5× web-ifc): trial as a
  faster **server** IFC→tessellation path behind the existing convert API. *Do not swap the browser engine.*
- **L4 — FreeCAD as an optional headless server engine** (LGPL, same `ifcopenshell` we run): parametric
  family generation + 2D-drawing export, additive to the pipeline, no client weight. Lower priority than L1.
- **glTF import overlay** + a one-click **pyRevit "export IFC → upload to Massing" macro** — both
  convenience niceties (glTF *export* + the pyRevit *export* path already ship), neither mission-critical.
- **RVT→IFC (APS) bridge polish** — the paid Autodesk Model-Derivative path already works behind a flag;
  incremental hardening only.

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213, ifcJSON/IFCX element+
  property export); only geometry authoring waits on web-ifc / Fragments IFC5 support (still alpha —
  §L "IFC5/IFCX"). Track buildingSMART; `@ifc-lite/parser` (L2) is the adopt-candidate once it stabilises.
- **Native mobile shell** — a **Capacitor wrapper** of the existing offline PWA (needs a macOS/Xcode +
  Android-SDK pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships today;
  the native shell is the fast-follow. See [mobile.md](mobile.md), §D.

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Wave 8 ⑦ regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent
  recordkeeping, Reg-D engine, escrow, the token) stays counsel-gated, licensed-platform work. Our
  origination-side **connector shipped v0.3.213** (`securities_bridge`, ledger sync, never moves money);
  build deeper only when a customer actually raises/syndicates. ⚖️ *Not legal advice; the partner is the
  licensed entity.* (Full decision in the Wave 8 §⑦ archive — [roadmap-completed.md](roadmap-completed.md).)

**⑥ Intentional non-goals — documented rationale (not gaps)**
- **In-browser IFC authoring** — Blender/Bonsai is the desktop editor by design (§L Pascal Editor); the
  web app stays a viewer + edit-gated place-tools. **`.mpp` (MS Project) parsing** — proprietary OLE binary,
  no reliable OSS reader; path is *Save As XML/CSV → import* (§L). **Custom Revit/Navisworks plugin** —
  Autodesk's certified `revit-ifc` already covers it (§L).
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled (favorites ↔ nav ↔
  persona events ↔ in-place DOM refresh); further extraction trades readability for indirection. The
  cleanly-separable pieces are already out (Wave 5).
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS integrations (flagged
  stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, and a
  JWT-revocation blacklist + Redis-backed presence (known limits, tracked in PRODUCTION_CHECKLIST).

**Recently cleared (were on this list):** capital-markets syndication connector + IFC5/IFCX data write path
(v0.3.213) · in-browser E57 reality-capture reader (v0.3.214) · cross-workspace deep-links both directions
(v0.3.211–212) · FF&E classification (v0.3.212) · B2 hashed `pip-compile` lockfiles (v0.3.198) · accounting
interop — approval-gated journal export (v0.3.199) + model-quantity WIP % by GlobalId (v0.3.200) · the whole
Wave 8 build ①–⑥ + ③b (v0.3.203–210).

---
