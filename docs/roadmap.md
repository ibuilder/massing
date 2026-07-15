# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.293**.

> **This file holds only what is still OPEN.** Everything shipped — every wave, track, and release —
> lives in [roadmap-completed.md](roadmap-completed.md), so *what's left* is never buried under *what's
> done*. The in-browser authoring initiative (P1–P6 + model browser / manage-levels / selection sets /
> edit-in-place), the product-feature roadmap, the code-quality/hardening waves (1–7), Wave 8 (all seven
> field-research tracks + the syndication connector), and the shipped parts of Waves 9–11 + AI-MCP are all
> in the archive. The Model workspace is now a genuine authoring+coordination program, not a viewer with
> buttons. What remains is incremental depth, spikes, upstream-blocked work, and documented non-goals —
> nothing is blocking.

---

## ⚡ Order of attack — the next ~8, highest value first

The Master Builder wave's headline deliverables have shipped — the **construction-document set** (plans /
sections / elevations / schedules → SVG·PDF·DXF + the 3-part project manual), **code intelligence**
(code-analysis, egress pre-check, jurisdiction-aware editions, approvability pre-flight, detail-rule
engine), **authoring guardrails + progressive disclosure**, and the **LOD-500 turnover layer**. What's left
deepens each track:

1. **G2 — field-verified dimensions / variances** — completes the LOD-500 data layer beside G1/G3.
2. **B3 — wall Axis rep + clippings/booleans** — sloped tops / gable walls (geometry depth; needs live-3D verification).

*(CODE-2 ✅ v0.3.295; D5 ✅ v0.3.296; W10-4 ✅ v0.3.297; S4 undo/redo ✅ v0.3.298; E1 inference ✅ v0.3.299; A1 sandbox ✅ v0.3.300.)*

---

## ⏳ What's left — the whole open roadmap, prioritized

Ordered most-actionable first; pull an item up on real customer need. Grouped by track for context, but the
order-of-attack above is the priority spine.

### 🧱 Wave 11 — The Master Builder (remaining)

The single architectural spine (multi-representation, view-keyed elements) + the guardrails and the drawing
generator already ship; these deepen geometry, drawings, code-intelligence, and the authoring UX.

**Construction-document generation (the CD set ships; these deepen it)**
- **C6 (remaining slices)** — reference-line datums (`IfcReferent`/`IfcVirtualElement`) and **"drawn detail
  follows LOD"** poché (representation selection + `IfcMaterialLayerSet` poché + annotation density →
  schematic single-line ↔ CD layered poché). Permissive libs only (no AGPL). *(DXF export + plans/sections/
  elevations/schedules → SVG·PDF·DXF + the project manual already ship — see the archive.)*

**Geometry depth → LOD 350/400**
- **B3** — wall **Axis representation + clippings/booleans** (sloped tops, gable walls).
- **B4** — **procedural-mesh escape hatch** (`add_mesh_representation` → `IfcTriangulatedFaceSet` for anything
  the parametric recipes can't express).
- **B5** — **connections / fasteners / hangers** + `IfcRelConnects*` (LOD-350 coordination).
- **F0b** — derive **Box / Axis / FootPrint** geometry on demand from `Body` (consumed by the C drawing generator).

**Code + spec + detail intelligence (IBC / MasterFormat)** — *D1 code-analysis, D3/D7 detail rules, D4
carriers, D6 project manual, D8 approvability pre-flight all ship (see the archive); these remain:*
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- ✅ **D5 SHIPPED v0.3.296** — **detail callouts** on the plan: an NCS-style divided-circle callout + a
  DETAILS legend for every element carrying an attached detail (`IfcRelAssociatesDocument`), distinct from
  the C2 keynote bubbles; `plan_svg` `details` toggle + count, flows into the SVG sheet. *(Keynotes-from-
  classification already ship via C2.) Next: detail callouts on the PDF sheet path + real sheet-number refs.*
- **D8 follow-ups** — wire COMcheck/energy-doc + A117.1 clearance checks into the pre-flight and round its findings to BCF.
- **`Pset_Massing_SpecLink` breadcrumb** — the remaining Track-D carrier.

**Open-ended authoring (the moat)**
- ✅ **A1 SHIPPED v0.3.300** — **sandboxed `execute_ifc_code`** (`sandbox.py`: AST allowlist, no
  imports/IO/reflection/dunder, curated namespace; off unless `AEC_ALLOW_IFC_CODE=1`; runs through the
  versioned/undo-able `/edit` path; ⚡ Run IFC code tool). *Next: A2 RAG index over ifcopenshell docs to
  ground code-gen, A3 AI emits recipes, A4 scene-digest.*
- **A2** — **RAG index** over ifcopenshell / IFC docs to ground code-gen.
- **A4** — LLM **scene-digest** tool over the semantic graph.

**Master-builder UX (low barrier)** — *E4 progressive-disclosure toolbar + E8 authoring-guardrails (first
slice) + E9 selector DSL ship (see the archive); these remain:*
- **E8 (deepen)** — extend the guardrails to nested `dims`, model-aware checks (host is a wall, storey exists), and the fuller "don't make broken IFC" rule set.
- ✅ **E1 SHIPPED v0.3.299** — **drawing inference** (`inference.ts`): automatic on-axis / parallel /
  perpendicular snapping from the previous point + edge, within ~6°, without holding Shift; hard
  geometry-vertex snap still wins; unit-tested. *Next: live inference guide-lines + a midpoint hover target.*
- **E2** — **type-a-dimension-while-drawing** (VCB).
- **E3** — **sketch-to-BIM push/pull** (2D profile → extrude).
- **E5** — **direct-manipulation parametric handles**.
- **E6** — **recipe-log undo/redo + design-option branches** (the recipe log *is* the undo stack).
- **E7** — **live schedules / quantities as you model**.

**LOD-500 verified-as-built data + content library** — *G1 as-built verify + G3 manufacturer/serial ship
(see the archive); these remain:*
- **G2** — field-verified dimensions / variances.
- **G3 follow-up** — warranty / O&M **document** refs via `IfcRelAssociatesDocument` (`attach_document` exists — wire an O&M-doc UI).
- **H1** — seed **CC0 furniture families + PBR materials** (CC0/CC-BY only — ambientCG, Poly Haven, Poly Pizza, Quaternius, Kenney, AMD MaterialX), attribution + license stored per asset.

**License guardrails (firm):** `ifcopenshell` + its geom serializers are **LGPL** — safe to depend on.
Reimplement drawing/annotation *techniques*, never vendor GPL code. SVG→PDF/DXF via permissive libs only
(**no AGPL** — no PyMuPDF). CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard.

### 🤖 AI-MCP / NL authoring (remaining)

S1–S3 ship (deterministic baseline → multi-step LLM interpretation, confirm-before-apply). Remaining:
- ✅ **S4 SHIPPED v0.3.298** — model **undo / redo** (`edit_history` sidecar stack + `POST /edit/{undo,redo}`
  + `GET /edit/history` + ↶/↷ toolbar buttons; GUID-stable version restore). The `/edit-preview` ghosting
  half already ships. *Next: multi-step undo grouping (one apply-all = one undo).*
- **S5** — multi-turn **clarifying questions**.
- Then **read tools** (quantities / schedules / clashes / violations) + an actual **MCP server surface**.

### 🏛️ Wave 10 — authoring-suite leftovers (not superseded)

- **W10-2** — **parametric family generators** (code-defined; typed params + optional formulas; profile
  library I/L/T/U/C/rect/circle + swept/boolean primitives so doors/windows/columns/casework are *generated*,
  not boxes). Freeform families via an optional **build123d (Apache-2.0) / OCP (LGPL)** track through
  `ifcopenshell.geom`. *Pure ifcopenshell for the core.*
- ✅ **W10-4 (first slice) SHIPPED v0.3.297** — **MEP port-to-port connectivity** (`connect_mep` recipe →
  `IfcRelConnectsPorts`) + `mep.connectivity` validation (ports connected/open, links, dangling elements;
  `GET /mep/connectivity`) + a two-step Connect flow in the 🔀 MEP tool. *Remaining: flow/sizing psets +
  coincident-port auto-connect.*
- **W10-5** — **annotation & tagging layer** (`IfcAnnotation` tags/dimensions/text/keynotes on the plan/section/elevation views).
- **W10-6** — **schedules & QTO** (`IfcElementQuantity` — *partly shipped via C4*; finish computed schedule/keynote-legend views into the export pipeline).
- **W10-7** — **structural analytical model** (`IfcStructuralAnalysisModel`, curve/surface members, point connections, load cases) — net-new domain alongside the physical model.
- **W10-9** — **parametric constraints & dimensional locks (the hard one)** — geometric constraint solving has no IFC representation; store constraints in a sidecar, solve, bake to IFC. Start with 1D/alignment locks. **License:** use FreeCAD's **planegcs (LGPL, extractable)**; *avoid python-solvespace (GPL) and OpenSCAD (GPL).*

### 🔬 Wave 9 — research-scan leftovers

- **W9-4 (harder half)** — ingest **specs / drawings / code documents** as graph nodes + an **NL→graph query with cited sources** (GUID + spec page + code section) — the explainability substrate under the W9-2 code-checks.
- **W9-5 (L part)** — smooth **equipment motion along paths** as the 4D slider advances + **swept crane-reach clash** (moving-equipment conflicts over time).
- **W9-6b** — a procedural **office space-planning generator** (headcount program → `IfcSpace` zones + furniture + auto BOM).
- **W9-7 — AI 2D-PDF auto-takeoff** *(optional / paid, flagged bridge)* — we already ship **manual** calibrated PDF takeoff; AI auto-extraction of quantities is proprietary/paid → a flagged bridge like the paid Autodesk RVT path, never core.
- **W9-8 — NL imperative authoring** *(largely covered by AI-MCP)* — "add a 2-hr fire wall between the corridor and the stair" → proposed recipe → confirm → apply. Folds into the AI-MCP track above.

---

## 🔐 Sign-in & first-run onboarding (open slices)

**Goal:** make social sign-in the prominent default and sequence it into the tutorial — *without* a hard
gate (the app runs free/offline without an account; a signup wall before the "aha" moment craters
top-of-funnel for open/self-hostable tools). We already have Google + Microsoft OAuth (config-gated, shown
above the password form), MFA, SSO/SAML/SCIM, and a first-run welcome modal + ≤5-step tour. This is
**prominence + flow**, not new auth. Grounded in social-login conversion data, reverse-trial/value-first
studies, and onboarding-benchmark research. Files: `apps/web/src/ui/onboarding.ts`, `apps/web/src/account/accountUI.ts`.

**First slice (one sprint — the core ask):**
- **B1 — optional sign-in as the welcome modal's first panel** *(M)* — a headline + one prominent
  **Continue with Microsoft** + **Continue with Google** (only the providers the server has configured, via
  `authProviders()`), a quiet "More options," and a clearly-visible **"Explore without an account →"** that
  drops to the existing quick-start cards. Prominent, never a wall.
- **B2 — sign-in → tour** *(S)* — after a successful sign-in *or* "Explore without an account", auto-launch
  the existing tour and `markOnboarded()` once.
- **A1 — keep Google + Microsoft as co-equal visible defaults** *(S)* — Microsoft is the B2B/M365-Azure AD
  pick our audience (GCs, developers, A/E) actually lives in; zero new backend.
- **A2 — collapse everything else behind "More sign-in options"** *(S)* — password, org SSO/SAML, Procore —
  kills six-logo decision paralysis at the highest-intent moment.
- **C1 — reorder the sign-in modal to lead with one big provider button + "More options"** *(S)* — match the
  first-run panel for consistency.

**Fast-follow:**
- **B3 — role self-selection right after sign-in** *(M)* — reuse the existing role picker as an inline step,
  then gear the tools rail / tour to that role (role personalization is ~+40% retention).
- **B4 — keep the tour ≤5 steps** *(S)* — repoint the old final "sign in" step now that sign-in moves to the
  front (completion drops >50% past 5 steps).
- **C2 — value-moment prompt** *(S)* — higher-contrast "Sign in" toolbar button + a "Sign in to save your
  work" affordance once a guest has created/modified something (ask after a win, not a wall).

**Deferred with explicit triggers:**
- **A3 — Sign in with Apple** *(M)* — web-only today means Apple's "must also offer Sign in with Apple" rule
  does **not** apply (it binds only a native App Store app that offers another social login). Build only
  alongside a native iOS wrapper; adds the $99/yr Apple Developer Program + a private-relay email path.
- **A4 — skip Facebook** (net-negative, consumer-coded, high in-app-browser failure) **and GitHub** (wrong
  audience); LinkedIn only if analytics show demand.
- **B5 — persistent quick-start checklist** *(L)* — checklist-launched tours convert best (~67%); a home for
  secondary discovery, deferred past the first slice.

*Privacy/mission guardrails: keep the guest/offline path fully functional; no telemetry/personal data before
consent; SSO buttons stay config-gated so self-hosters don't advertise providers they haven't set up.*

---

## 🔮 Future — 2026-07 research inbox (building codes · Unreal viz)

Parked as **future** items — not scheduled; picked up after the current Wave 11 tracks. Each notes size +
value; license/legal flags are firm.

### 🏛️ Building-code library (jurisdiction-aware code compliance)
The copyright-safe strategy: **own the rules, facts, and checks; deep-link out for prose; license prose later.**
**GREEN (do freely):** store section numbers/titles/edition years, jurisdiction→adopted-edition **adoption
facts**, numeric thresholds/formulas (facts of law — exactly what `codecheck.py` already encodes), and **our
own paraphrased** rule content. **RED (never):** scraping/redistributing ICC/ASTM verbatim **prose** — the
relevant fair-use rulings are preliminary/unresolved and a commercial SaaS reproducing code text is the exact
market-harm scenario in active litigation.
*(✅ **CODE-1 catalog** (`codes.py`) and **CODE-3 first slice** (edition-aware code-analysis) ship — see the
archive. These extend them:)*
- **CODE-1 follow-ups** — extend the per-state adoption seed from authoritative sources (ICC adoptions DB + DOE energy-code status) and add per-project jurisdiction storage.
- ✅ **CODE-2 (first slice) SHIPPED v0.3.295** — edition-scoped **occupant-load factors** threaded through
  `egress_analysis`/`egress_from_model` (the Business 100→150 gross change at IBC 2018); `code_analysis`
  resolves the jurisdiction's edition and computes the load with it. *Next: externalize the fuller `_RULES`
  threshold table into edition-scoped rows + `resolve_code_context(location, date)` as more deltas are encoded.*
- **CODE-3 (deepen)** — thread the resolved edition into the Track-D detail-rule citations so an exterior window cites the *actually-adopted* section.
- **CODE-4** *(S · med)* — local-amendment overlay model + manual-entry UI (store *our summary* + a link, not a third-party compilation).
- **CODE-5** *(M · med)* — emit `CodeRule`s as **buildingSMART IDS** XML so the same jurisdiction-resolved
  rules validate IFC via any IDS checker (extends our IDS→BCF pipeline).
- **CODE-6** *(L · med, flagged/paid)* — licensed **prose** integration behind a feature flag + cost warning,
  mirroring the paid Autodesk RVT-bridge pattern. Only after CODE-1–3 prove demand — a contract/cost commitment, not code risk.

### 🎮 Unreal Engine — one-way viz export only (never core)
Honest verdict: Unreal **breaks offline, doesn't author, and carries royalty/seat licensing** — categorically
incompatible with our permissive/offline core. Datasmith **does** preserve GlobalId + metadata as runtime
tags, but strictly **one-way (viz only)**.
- **VIZ-1** *(S · high · ON-MISSION)* — **glTF/`.glb` (and optional `.udatasmith`) export** from our
  ifcopenshell pipeline, feeding Unreal/Twinmotion **and** better web viewers with zero engine-license
  exposure. **NOTE: largely shipped — a glTF export path already exists; confirm parity / fill gaps.**
- **VIZ-2** *(S/M · on-mission)* — **three.js PBR "presentation mode"** (IBL/HDRI, SSAO/bloom, baked
  lightmaps) — ~90% of "impress the client" value while staying offline + license-free.
- **VIZ-3** *(L · optional/paid/flagged)* — pixel-streamed cinematic mode (cloud-GPU → WebRTC to a browser
  tab, on-demand). License-gated + per-session GPU cost; marketing/high-end only, never the default viewer.
- **VIZ-4** *(L · optional/paid/flagged)* — VR design-review bridge (Datasmith IFC → Unreal, GlobalId tags →
  click-through to our API). An optional interop tier, not core.

### 🚀 Model-authoring & collaboration frontier
The high-value net-new bets validated by the field: an **AI/NL layer over the model** (validating our AI-MCP
track) plus real-time collaboration and live site/proforma loops. Keep our IFC-native + openBIM round-trip
and CD/detailing depth as the moat.
- **AI-MCP / NL authoring** *(M · ★★★★★)* — natural-language authoring over our edit-recipe engine, IFC-native.
  **S1–S3 ship** (see the AI-MCP track above); next is S4/S5 + read tools + an MCP server surface.
- **COLLAB-1** *(L · ★★★★★)* — **real-time multiplayer co-editing** (presence, cursors, live-streamed edits) +
  lightweight **in-model comments** — the biggest gap for a browser-based modeling tool.
- **SITE-1** *(M · ★★★★)* — **auto site context + parcel/zoning-envelope ingestion** for a North-American
  address (parcel geometry, setbacks/height/FAR → buildable envelope); feeds authoring + the code engine.
- **PROFORMA-LIVE** *(M · ★★★★)* — tighten the **model↔proforma live loop**: yields/unit-mix/parking/efficiency
  + cost recompute **inline as you model**, not only in the portal.
- **COST-AGENT** *(M · ★★★★)* — an estimating agent that re-estimates on each geometry change + learns from
  historical cost data (companion to AI-MCP + the estimating→5D track).
- **BOARDS** *(M · ★★★½)* — a "Boards" presentation surface: styled design-option views, shadow studies,
  auto-generated stakeholder decks as first-class artifacts alongside sheets.
- **NL-QA** *(S · ★★★½)* — built-in natural-language QA recipes once AI-MCP matures ("audit issues + suggest
  fixes," "check room accessibility," "normalize inconsistent Psets"). Maps onto code-check + model-hygiene.
- *Validated / overlap (verify, don't rebuild):* bulk IFC Pset editor (⊂ our override layers), manufacturer
  product-configurator → IFC type (⊂ families/types), in-context comments (⊂ BCF — the gap is a lightweight
  authoring-surface comment).

---

## 🚧 Blocked, deferred & non-goals

**④ Blocked upstream — revisit when the dependency lands**
- **IFC5 / IFCX *geometry* write** — the **data** write-path shipped (v0.3.213, ifcJSON/IFCX element+property
  export); only geometry authoring waits on web-ifc / Fragments IFC5 support (still alpha). Track buildingSMART.
- **Native mobile shell** — a **Capacitor wrapper** of the existing offline PWA (needs a macOS/Xcode +
  Android-SDK pipeline separate from the Tauri desktop release). PWA "Add to Home Screen" ships today; the
  native shell is the fast-follow. See [mobile.md](mobile.md).

**⑤ Deferred by decision — integrate, don't build (pursue on customer pull)**
- **Regulated syndication depth** — the licensed stack (KYC/accreditation, transfer-agent recordkeeping,
  Reg-D engine, escrow, the token) stays counsel-gated, licensed-platform work. Our origination-side
  **connector shipped v0.3.213** (`securities_bridge`, ledger sync, never moves money); build deeper only when
  a customer actually raises/syndicates. ⚖️ *Not legal advice; the partner is the licensed entity.* (Full
  decision in the archive — [roadmap-completed.md](roadmap-completed.md).)

**⑥ Intentional non-goals — documented rationale (not gaps)**
- **In-browser IFC authoring** — **REVERSED (2026-07): now a first-class, shipped capability** (from-scratch
  models, GUID-stable draw/edit recipes, drag-to-move, model browser, manage levels, selection sets). Blender/Bonsai
  remains an *optional* advanced/interop editor. **`.mpp` (MS Project) parsing** — proprietary OLE binary, no
  reliable OSS reader; path is *Save As XML/CSV → import*. **Custom Revit plugin** — the certified `revit-ifc`
  exporter already covers it.
- **A4/A5 portal-core split** — the catalog↔nav orchestration is deliberately coupled; further extraction
  trades readability for indirection. The cleanly-separable pieces are already out (Wave 5).
- **Out-of-scope-by-design operations integrations** — live ENERGY STAR / BAS / BMS integrations (flagged
  stubs only), full institutional reporting packs, space/move management (CAFM), 1031 tooling, and a
  JWT-revocation blacklist + Redis-backed presence (known limits, tracked in PRODUCTION_CHECKLIST).
