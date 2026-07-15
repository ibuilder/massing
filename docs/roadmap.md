# Roadmap

The single product roadmap. Supporting detail lives in:
[production-readiness.md](production-readiness.md) (security/perf/ops checklist),
[gc-portal.md](gc-portal.md), [gc-tools-audit.md](gc-tools-audit.md),
[ux-findings.md](ux-findings.md).

Three pillars on one IFC-keyed model: **BIM viewer** · **GC portal** (config-driven modules) ·
**developer/finance** (proforma). Shipped continuously — latest release **v0.3.280**.

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

*(CD set finished: DXF export ✅ v0.3.281, schedules-on-a-PDF-sheet ✅ v0.3.282.)*

1. **B3 — wall Axis rep + clippings/booleans** — sloped tops / gable walls (unblocks real geometry depth).
2. **CODE-2 — externalize codecheck thresholds → edition-scoped `CodeRule`** — makes the checker edition-aware (CODE-1 catalog ✅ v0.3.285).
3. **D5 — keynotes & detail callouts from classification** — closes the attach-code → keynote-on-plan loop.
4. **S4 — authoring confirm-UX** — `/edit-preview` ghosting + revert-to-version undo for NL authoring.
5. **A1 — sandboxed `execute_ifc_code` recipe** — turns the fixed recipe registry into unbounded authoring.
6. **W10-4 — MEP systems connectivity & sizing depth** — fully-connected logical systems + validation.

*(E4 progressive-disclosure toolbar ✅ v0.3.283; E8 authoring guardrails first slice ✅ v0.3.284.)*

---

## ⏳ What's left — the whole open roadmap, prioritized

Ordered most-actionable first; pull an item up on real customer need. Grouped by track for context, but the
order-of-attack above is the priority spine.

### 🧱 Wave 11 — The Master Builder (remaining)

The single architectural spine (multi-representation, view-keyed elements) + the guardrails and the drawing
generator already ship; these deepen geometry, drawings, code-intelligence, and the authoring UX.

**Construction-document generation (finish the CD set) — highest value**
- **C6 (near-term slices)** — ✅ **DXF export SHIPPED v0.3.281** (`dxf.py` R12 writer + plan/section/elevation
  `.dxf` endpoints; dependency-free); ✅ **schedules-on-a-PDF-sheet SHIPPED v0.3.282** (`drawing.schedule_pdf`
  on an ARCH-D titleblock sheet + `GET /drawings/schedule.pdf`). Remaining: reference-line datums
  (`IfcReferent`/`IfcVirtualElement`) and **"drawn detail follows LOD"** poché (representation selection +
  `IfcMaterialLayerSet` poché + annotation density → schematic single-line ↔ CD layered poché). Permissive
  libs only (no AGPL).

**Geometry depth → LOD 350/400**
- **B3** — wall **Axis representation + clippings/booleans** (sloped tops, gable walls).
- **B4** — **procedural-mesh escape hatch** (`add_mesh_representation` → `IfcTriangulatedFaceSet` for anything
  the parametric recipes can't express).
- **B5** — **connections / fasteners / hangers** + `IfcRelConnects*` (LOD-350 coordination).
- **F0b** — derive **Box / Axis / FootPrint** geometry on demand from `Body` (consumed by the C drawing generator).

**Code + spec + detail intelligence (IBC / MasterFormat)**
- **D2** — **routed egress / life-safety plans** (path-trace over the W9-4 semantic graph, not just tabulated).
- **D5** — **keynotes & detail callouts** on drawings, generated *from* the element's classification (NCS UDS Module 7).
- **D6** — **3-part MasterFormat project manual** (group by MasterFormat → SectionFormat Part 1/2/3; Part 3 Execution = attached install instructions).
- **D8** — **approvability pre-flight** (reviewer checklist: UL/GA numbers on rated walls, egress traced, COMcheck attached, A117.1 clearances) — extends the IDS→BCF pipeline.
- **`Pset_Massing_SpecLink` breadcrumb** — the remaining Track-D carrier.

**Open-ended authoring (the moat)**
- **A1** — **sandboxed `execute_ifc_code` recipe** (AST-whitelisted, ifcopenshell-only, no fs/Blender) — turns the fixed recipe registry into unbounded authoring.
- **A2** — **RAG index** over ifcopenshell / IFC docs to ground code-gen.
- **A4** — LLM **scene-digest** tool over the semantic graph.

**Master-builder UX (low barrier)**
- ✅ **E8 (first slice) SHIPPED v0.3.284** — **authoring guardrails** (`guards.py::precheck` enforced in
  `apply_recipe` + `POST /edit/precheck`): finite coords, no zero-length lines, positive dims, valid enums,
  required refs; blocks broken edits, warns on unit-slip magnitudes. *Next: extend to nested `dims`,
  model-aware checks (host is a wall, storey exists), and the fuller rule set.*
- ✅ **E4 SHIPPED v0.3.283** — **progressive-disclosure toolbar**: everyday authoring + drawing tools visible; LOD-350/400 fabrication + detailing tools behind a persisted "🔧 Advanced fabrication tools" toggle.
- **E1** — **inference snapping** (endpoint/mid/face/parallel/perp) + Shift-lock.
- **E2** — **type-a-dimension-while-drawing** (VCB).
- **E3** — **sketch-to-BIM push/pull** (2D profile → extrude).
- **E5** — **direct-manipulation parametric handles**.
- **E6** — **recipe-log undo/redo + design-option branches** (the recipe log *is* the undo stack).
- **E7** — **live schedules / quantities as you model**.

**LOD-500 verified-as-built data + content library**
- **G2** — field-verified dimensions / variances.
- **G3** — external-doc refs (warranties/O&M/serials) + Manufacturer/Serial psets (`Pset_ManufacturerTypeInformation`/`Pset_ManufacturerOccurrence`) via `IfcRelAssociatesDocument`.
- **H1** — seed **CC0 furniture families + PBR materials** (CC0/CC-BY only — ambientCG, Poly Haven, Poly Pizza, Quaternius, Kenney, AMD MaterialX), attribution + license stored per asset.

**License guardrails (firm):** `ifcopenshell` + its geom serializers are **LGPL** — safe to depend on.
Reimplement drawing/annotation *techniques*, never vendor GPL code. SVG→PDF/DXF via permissive libs only
(**no AGPL** — no PyMuPDF). CC0 asset sources vetted per-asset. IDS is an open buildingSMART standard.

### 🤖 AI-MCP / NL authoring (remaining)

S1–S3 ship (deterministic baseline → multi-step LLM interpretation, confirm-before-apply). Remaining:
- **S4** — confirm-UX + `/edit-preview` **ghosting** + **revert-to-version** undo.
- **S5** — multi-turn **clarifying questions**.
- Then **read tools** (quantities / schedules / clashes / violations) + an actual **MCP server surface**.

### 🏛️ Wave 10 — authoring-suite leftovers (not superseded)

- **W10-2** — **parametric family generators** (code-defined; typed params + optional formulas; profile
  library I/L/T/U/C/rect/circle + swept/boolean primitives so doors/windows/columns/casework are *generated*,
  not boxes). Freeform families via an optional **build123d (Apache-2.0) / OCP (LGPL)** track through
  `ifcopenshell.geom`. *Pure ifcopenshell for the core.*
- **W10-4** — **MEP systems connectivity & sizing depth** (`IfcDistributionSystem`, `IfcRelConnectsPorts`,
  `IfcRelNests`, flow/sizing Psets, system browser + connectivity validation).
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
- ✅ **CODE-1 SHIPPED v0.3.285** — jurisdiction + adoption **facts** catalog (`codes.py`: code families +
  editions on the 3-year cycle, `resolve(jurisdiction)` → adopted editions with a national-baseline fallback,
  mandatory verify-with-AHJ note + as-of year; `GET /codes/{families,adoptions,seeded}` + an Adopted-codes
  lookup in the code-analysis tool). Copyright-safe (facts only). *Seed is a dated starting point — extend
  the per-state adoptions from authoritative sources (ICC adoptions DB + DOE energy-code status); add
  per-project jurisdiction storage next.* Unlocks CODE-2/3.
- **CODE-2** *(M · high)* — externalize `codecheck.py` thresholds (`_RULES`/`_OCC_FACTORS`/egress constants)
  into **edition-scoped `CodeRule` rows** + `resolve_code_context(location, date)`; thread `code_ctx` through
  `egress_analysis`. Edition-aware (2015/2018/2021/2024) vs "generic latest," with an IBC-2021 fallback seed.
- **CODE-3** *(M · high)* — edition-aware citations in the **Track-D detail-rule engine** (an exterior window
  cites the project's *actually adopted* IBC section).
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
