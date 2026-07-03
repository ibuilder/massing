# Changelog

All notable changes to Massing. Releases are signed, auto-updating desktop builds
(Windows / macOS / Linux); the updater always serves the latest. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

## v0.3.53 — Production hardening: backend blockers (readiness R1 of 7)
From a full production-readiness audit (code + docs + deployment). Fixes the findings that make the
difference between "works in dev" and "safe under load, multi-worker, and misconfiguration":
- **Fail-fast production guard** — booting on **Postgres** without `AEC_RBAC=1` or with the default
  auth secret now **refuses to start** (explicit `AEC_ALLOW_OPEN=1` escape hatch). A forgotten env var
  is a loud crash at boot, not an open platform discovered later. CRITICAL log when the rate limit is
  on with multiple workers but no shared Redis counter.
- **Project list scales + doesn't leak** — `GET /projects` filters membership in SQL (join) instead of
  loading every project then running one role query each (N+1), and is paginated.
- **Bounded loads everywhere** — kanban `board()` returns capped per-state cards plus TRUE counts from
  a GROUP BY (was: materialize up to 100k records per request); CSV export **streams** page-by-page;
  the list `?limit=` param is clamped; Procore sync reads only the `procore_id` column via SQL json
  extraction (was: `limit=1_000_000` full-record load).
- **Observability** — fragment-conversion and publish failures now `logging.exception` (they were
  visible only in a status JSON nobody polls); auto-sync schedule failures log at WARNING.
- **Multi-worker autosync** — a Postgres advisory lock elects one runner per tick, so N workers no
  longer each pull the same external records.
- **Uploads & traversal** — the properties-index upload is size-gated (413 over `AEC_PROPS_MAX_MB`,
  default 100); attachment filenames explicitly collapse `..` sequences (belt on top of the existing
  storage containment guard).
- **Complete project deletion** — deleting a project now removes the **whole `{pid}/` storage prefix**
  (source-IFC copies, props index, publish status — not just the model tile) via a new
  `storage.delete_prefix` on both local and S3 backends.
- **Rate limiter** — evicts oldest buckets under IP churn instead of clearing all state at once.
- Verified: new `test_prod_hardening` + adjacent regressions (modules/rbac/security/connections/api/
  bcf) green, ruff + bandit clean.

## v0.3.52 — Architect sign-off + G704 substantial completion + record turnover (lifecycle track 4 of 4)
The final track closes the loop to turnover: the **Architect certifies substantial completion**, signs
off the punch list, and the as-built **record model** is stamped for handover.
- **`turnover.py` + `/turnover/*` endpoints** — `readiness` (punch rollup + latest model version; a
  G704 certifies *with* an open punch list, so the gate is that a punch list is prepared), `certify`
  (Architect certifies on a `completion_certificate` record: records the **Architect (certifying) +
  Owner + Contractor** signatures, stamps the current model version as the record model, issues the
  certificate), and `status` (signed cert + record-model summary).
- **G704 Certificate of Substantial Completion** generator in `contracts.py` — attaches the punch-list
  summary, the record-model version, and the occupancy date; reachable via
  `…/contracts/completion_certificate/{rid}/document.pdf?doc=g704`. The **Architect** is now a signatory
  on the G701 change order too.
- **Turnover package** — `closeout/package.zip` gains `turnover/status.json` (readiness + signed
  substantial-completion cert + record model version) alongside the as-built model, COBie and closeout
  manifest. `completion_certificate` gains occupancy-date / record-model-version / punch-% fields.
- **UI** — a **"🏁 Turnover"** construction-workspace panel: punch readiness, architect certification
  (with signatories), and one-click **G704** download.
- Verified: ruff + bandit clean, backend gate (new `test_turnover` — gate refuses with no punch list;
  architect certifies + Owner/Contractor sign; G704 renders; status reflects the signed cert) +
  `test_contracts`/`test_closeout` regressions, web typecheck + 49 vitest + Pages build + budget green.

**This completes the architect/engineer design-to-turnover lifecycle upgrade (4 tracks, v0.3.49–52).**

## v0.3.51 — Design-change instruments: ASI / Bulletin / Sketch (lifecycle track 3 of 4)
The standard AIA construction-phase change instruments, wired into the existing change chain.
- **New modules `asi`, `bulletin`, `sketch`** (Change Management section, config-driven CRUD + workflow):
  - **ASI** (AIA G710) — the Architect issues a supplemental instruction; **no cost/time**; the
    Contractor acknowledges (`issued → acknowledged → closed`).
  - **Bulletin** — a formal design revision; when it carries cost/time it links to a `change_event`
    (→ `pco_request → cor`) for pricing (`draft → issued → priced → closed`).
  - **Sketch (SK)** — a clarification sketch that attaches to an ASI / Bulletin / RFI / drawing.
- **Document generation** — G710 ASI + Bulletin cover-sheet + **G714 Construction Change Directive**
  (rendered from a `directive` record) added to `contracts.py`; all reachable through the existing
  `GET /projects/{pid}/contracts/{key}/{rid}/document.pdf?doc=asi|bulletin|ccd`. `directive` is the
  platform's CCD (G714) instrument.
- Verified: ruff + bandit clean, `test_change_instruments` (ASI issue→ack no cost; Bulletin cost impact
  links a change_event; SK attaches; ASI/Bulletin/CCD render as PDFs) + `test_contracts` regression,
  web typecheck green.

## v0.3.50 — IFC family library (lifecycle track 2 of 4)
The "families" folder now ships real `.ifc` content and a browsable library, fully offline.
- **Generated parametric core library** — `build_family_library.py` writes the whole catalog to a
  shippable **`services/data/families/library.ifc`** (46 families, each a GUID-stable `IfcTypeProduct`
  with mapped geometry, IFC4). The catalog gained **openings** (single/double door, fixed/sliding
  window), **enclosure** (interior partition, exterior wall, curtain-wall panel), and **concrete
  columns/beams** on top of the existing furniture / sanitary / appliance / lighting / MEP /
  structural / transport / plant families.
- **Family-library server** — `GET /families/library` (generated catalog grouped by category +
  the generated library + any curated external files) and `POST /projects/{pid}/families/place`
  (place a library family, GUID-stable, via the `add_family` recipe). The viewer's **Furnish & equip**
  picker now reflects the full library and its family count.
- **Curated external** — `services/data/families/external/` with a `SOURCES.md` of vetted free openBIM
  sources (buildingSMART samples, opensourceBIM/IFC-files, NBS National BIM Library, bSDD); drop an
  `.ifc` there or use `POST /families/import` to bring in manufacturer content. No third-party binaries
  are bundled without explicit review.
- Verified: ruff + bandit clean, backend gate (new `test_family_library` — library builds + reopens +
  place-from-library), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.49 — Design-phase spine + itemized soft costs (lifecycle track 1 of 4)
Makes the architect/engineer design lifecycle explicit. Grounded in the RIBA Plan of Work 2020 (stages
0–7) mapped to the AIA design phases (Schematic Design → Design Development → Construction Documents →
Construction Administration), ISO 19650 information stages, and standard development soft-cost / design-
fee breakdowns.
- **`design_phase.py` + `project_phase` module** — the eight RIBA/AIA phases as **formal gates**. Each
  phase carries its deliverables, A/E design-fee %, and ISO-19650 status (S0→AM); the gate advances only
  when the **Architect + Owner** sign it off (`approve_gate` transition, requires a signer). Generating a
  project now seeds the eight phases automatically.
- **`soft_costs.py` — itemized, phase-aware soft costs** — the flat "soft = 25% of hard" is replaced by
  a transparent taxonomy (architecture & engineering fee, permits/entitlements, legal, financing &
  interest, insurance & bonds, developer fee, FF&E, marketing/lease-up, soft contingency). Totals are
  unchanged by default, but the **A/E design fee is drawn down across SD/DD/CD/Bid/CA** per standard
  splits. The generate seed (`_seed_dev_budget`, `_proforma_seed`) now emits itemized soft-cost lines.
- **Endpoints** `GET /projects/{pid}/lifecycle` (phases + gate state + soft-cost allocation + current
  stage), `POST …/lifecycle/seed`, `GET /lifecycle/reference`. New **"🧭 Project Lifecycle"** developer-
  workspace panel: the phase rail with deliverables, fee %, ISO status, gate sign-off, and the itemized
  soft-cost table.
- Verified: ruff + bandit clean, backend gate (new `test_design_phase`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.48 — Hardening, accessibility & documentation pass
A quality pass over the recently-shipped features: debug + full test sweep, a security-hardening
review, accessibility on the new UI, and a documentation refresh.
- **Security — outbound-URL guard.** New `net.py` `validate_outbound_url()` gates the bridges that
  fetch an **operator-configured** URL — **webhooks**, the real-estate syndication bridge, and the
  e-sign bridge — rejecting non-http(s) schemes (blocks `file://` / `gopher://` local-file-read + SSRF
  vectors) with an opt-in private-host check. The fixed-provider fetches (Autodesk, Google/Microsoft
  OAuth, Procore) and the already-guarded Speckle bridge were reviewed and left as-is.
- **Accessibility.** The new **Land Screening**, **IDS Requirements** and **conceptual-estimate**
  forms had placeholder-only inputs; every field now carries an `aria-label` so screen readers
  announce it. All new destinations confirmed reachable from the workspace nav (native `<button>`s,
  keyboard-operable).
- **Tests.** New `test_net`; backend gate now **97/97** suites. Web typecheck + 49 vitest + Pages
  build + bundle budget (156 KB shell < 220 KB) all green. `ruff` + `bandit` clean.
- **Docs.** Competitive/vendor comparison removed from the documentation set (README, the public
  landing page, the lifecycle graphic, roadmap/audit notes) in favor of neutral capability language;
  integration/connector references (Procore SSO + sync, ACC, QuickBooks/Sage) are retained as the
  factual product features they describe. README "Recent work", CHANGELOG and the GitHub About refreshed
  to current state; stale internal links removed.

## v0.3.47 — Land parcel screening + data connector
Land acquisition screening. The nationwide parcel dataset is a licensing play, so it's a
feature-flagged connector; the pure-software win — which plays to our GIS + feasibility + proforma
engines — is **screening**.
- **`parcels.py`** — screen a parcel set (imported GeoJSON / entered) by **size, zoning, flood zone,
  sewer/water, price**, and **rank by max-buildable opportunity**: each parcel gets a max envelope
  (area × FAR) and a **conceptual cost** (via `conceptual_estimate`), plus **land cost per buildable SF**
  — a screen → envelope → proforma chain that runs before acquisition, not just after.
- **`parcels_bridge.py`** — nationwide parcel/ownership/comps data is an optional paid connector
  (`PARCEL_PROVIDER`, Regrid/ATTOM/CoreLogic pattern) that raises rather than shipping fake data; the
  screening engine works on parcels you supply without it.
- Endpoints: `POST /parcels/screen`, `GET /parcels/data-status`. A **🗺️ Land Screening** developer-
  workspace panel (paste parcels → set criteria → ranked buildable-opportunity table).
- Verified: ruff clean, 96/96 backend suites (new `test_parcels`), web typecheck + 49 vitest + Pages
  build + budget green.

**This completes the second capability round (4 tracks, v0.3.44–47) on top of the code-quality gate
(v0.3.43).**

## v0.3.46 — Conceptual estimating + AI IFC classification
Two model-native intelligence features that leverage our IFC/massing strengths.
- **`conceptual_estimate.py`** — a parametric **$/SF** cost from building type + GFA + units at the
  massing stage (on-brand for a product called Massing): a low/base/high range **escalated for region
  and year**, with derived $/SF, $/unit and $/key for the proforma before there's a detailed takeoff.
  Built-in cost-per-SF table (16 building types) + regional index + ~4.5%/yr escalation, all overridable.
- **`ifc_classify.py`** — a transparent rules classifier that suggests the right **IfcClass** for
  `IfcBuildingElementProxy`/generic or mis-named elements (a proxy gets no quantity or carbon factor, so
  this directly improves **QTO + embodied carbon** accuracy). Every suggestion carries its reason;
  human-approved — reads the loaded property index or a posted element list.
- Endpoints: `GET /estimate/conceptual/catalog`, `POST …/estimate/conceptual`, `POST …/ifc/classify`.
  Surfaced in the **🛡 Risk & Cost** panel (a $/SF estimate mini-form + a model-classification summary).
- Verified: ruff clean, 95/95 backend suites (new `test_conceptual`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.45 — Materials procure-to-pay: quote leveling + 3-way match
The materials buying loop — distinct from sub-bid leveling. Deterministic/offline on top of the
modules we already have (`commitment` = PO, `delivery`, `sub_invoice`).
- **`procurement.py` — quote leveling** — normalize competing supplier quotes into an apples-to-apples
  grid with the low price per line item, the best-value supplier, per-supplier totals, and line-by-line
  savings (handles split awards where the cheapest supplier differs per item).
- **3-way match** — reconcile each PO against its deliveries and invoices, flagging **over-billing**
  (invoiced > PO), **pay-before-receipt** (invoiced with nothing received), and **un-invoiced
  deliveries**. Surfaced in the **🛡 Risk & Cost** panel.
- **`procurement_bridge.py`** — RFQ dispatch to suppliers is a feature-flagged stub (`RFQ_PROVIDER`)
  that raises rather than pretending to send; the *quote leveling* and *3-way match* work without it.
- Endpoints: `POST /projects/{pid}/procurement/level-quotes`, `GET …/three-way-match`, `/procurement/rfq-status`.
- Verified: ruff clean, 94/94 backend suites (new `test_procurement`), web typecheck + 49 vitest +
  Pages build + budget green.

## v0.3.44 — IDS authoring + EIR
Closing the BIM-standards loop upstream. We already *validate* models against an IDS; the demand is
upstream of that — **authoring** the requirements in the first place.
- **`ids_authoring.py`** — a starter requirements template library (what data each element type should
  carry: walls → FireRating/LoadBearing/…, doors, windows, slabs, spaces, columns, beams — from the
  standard `Pset_*Common` sets), bundled into **use cases** (handover/COBie, fire & life safety, energy,
  quantities). `build_ids()` emits a **standards-valid buildingSMART IDS 1.0** file via `ifctester` that
  **round-trips through our own validator**, and `eir_markdown()` generates an **EIR** (Exchange
  Information Requirements) document for the BIM contract.
- Endpoints: `GET /ids/templates`, `POST /ids/build` (→ downloadable `.ids`), `POST /ids/eir` (→ EIR.md).
  Model compliance-checking stays the existing `/validate` endpoint — closing the spec → implement →
  validate loop.
- **UI:** a **📋 IDS Requirements** portal panel — pick a use case, preview the required properties,
  download the IDS + EIR.
- Verified: ruff clean, 93/93 backend suites (new `test_ids_authoring` round-trips the IDS through
  ifctester), web typecheck + 49 vitest + Pages build + budget green.

## v0.3.43 — Code-quality gate (ruff + bandit in the loop) + BCF XXE fix
Applying the "enterprise-quality code with AI agents" discipline — verification *in the loop*, not after.
- **Static-analysis gate (ruff)** — a tuned config (`services/api/ruff.toml`) enforces the high-signal
  rules that catch real defects and dead code (pyflakes `F`, syntax `E9`, bugbear `B`) while respecting
  the codebase's deliberate idioms (compact `;` one-liners; the logged fail-open `except Exception`
  pattern is *not* linted). Wired into CI as a **blocking** step. Fixed everything it found: **14 unused
  imports + 2 unused variables** (dead code removed) and a **loop-variable closure bug** in the BCF
  camera parser.
- **Security scan (bandit)** — added to the report-only security workflow and run before shipping. It
  surfaced a real one: **`bcf_io.py` parsed untrusted uploaded BCF XML with the vulnerable stdlib
  parser (XXE / billion-laughs vector)** — now uses **`defusedxml`**, the same hardening already applied
  to CityGML import. Fixes an actual vulnerability on the BCF import path.
- `ruff` + `bandit` added to `requirements-dev.txt`; `CONTRIBUTING.md` documents the local gates.
- Verified: ruff clean, 92/92 backend suites, bandit XXE finding resolved.

## v0.3.42 — Tiers 2 & 3: fintech depth + differentiated (carbon, code, pricing)
The rest of the capability roadmap. Every engine is offline/deterministic (AI only where it helps),
source-linked, and never fabricates; money movement and live pricing are feature-flagged bridge stubs
that raise actionable errors rather than faking a result.
- **Subcontractor prequalification** — a transparent Q-score (safety/EMR, financial, experience, rating,
  currency = 100 pts, every point traceable) + a **COI-expiry** feed. A single sub default costs a GC
  1.5-3× the subcontract, so this is a core risk gate before award.
- **Pay-app ↔ lien-waiver reconciliation** — matches what was **paid** (`sub_invoice`) against **waivers**
  on file (`lien_waiver`, conditional vs unconditional) and surfaces per-vendor **lien exposure**. Massing
  never moves money: a `payments_bridge` stub disburses only through a licensed processor and refuses
  release while exposure remains.
- **Accounting export** — double-entry **GL CSV** + **QuickBooks IIF** bills from the cost records, so
  finance stops re-keying. (Live two-way sync remains the connection framework's job.)
- **Embodied carbon (A1-A3)** — computed from `production_quantity` × a built-in EPD factor table with
  unit conversion, rolled up by material + cost code. Zero of this existed before, and it plays to our
  IFC/quantity strength as embodied-carbon reporting goes mandatory on public work.
- **Code-compliance assistant** — describe a project → applicable **IBC/ADA/IECC** sections with citations
  (Claude when keyed; a deterministic IBC checklist triggered by occupancy/area/stories otherwise).
- **Takeoff pricing** — reconcile the takeoff to a built-in unit price book (+ a `pricing_bridge` stub for
  a live supplier/RSMeans feed) with **variance vs the estimate**.
- **UI:** a **🛡 Risk & Cost** portal panel (prequal scores, COI expiry, lien exposure, carbon, priced-
  takeoff variance, GL/IIF export) and a **Code check** tab in AI Assist.
- Verified: 92/92 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.41 — Tier 1: AI drafting, bid leveling, cross-project benchmarking
Market-driven upgrades. Each AI engine mirrors the existing
`review.py`: Claude when `ANTHROPIC_API_KEY` is set, a deterministic **offline fallback** otherwise,
every output **source-linked**, never fabricated; heavy calls run off the event loop and are throttled.
- **AI drafting** (`drafting.py`, **AI Assist** panel) — turn a note or a PDF into an editable
  first-draft **RFI**, **submittal summary**, or trade **scope of work** with page citations, so teams
  stop retyping from documents (the report's "18% of project time is spent searching for data").
  Human-in-the-loop: nothing is created until you click **Create**.
- **Bid leveling** (`bid_leveling.py`) — level a package's `bid_submission` records into an
  apples-to-apples grid: base-bid stats + >25% **outlier** flags, a **scope matrix** (who includes/
  excludes each item), **scope-gap** detection, and a **scope-adjusted low** recommendation (a low bid
  missing scope others carry is flagged). Optional AI canonicalizes free-text scope phrases.
  `GET /projects/{pid}/bids/leveling/{package_rid}`; shown as a grid in the AI Assist panel.
- **Cross-project benchmarking** (`benchmarking.py`, **Benchmarks** panel) — your own history across
  every project: actual **cost distribution** (low/p25/median/p75/high) per cost code, and RFI/submittal
  **turnaround + overdue %** (ball-in-court accountability). Answers the survey's "76% aren't realizing
  their data's potential." `GET /benchmarks/costs`, `/benchmarks/response-rates`.
- **Test-gate fix:** `run_tests.py` used a hardcoded list that silently skipped 12 on-disk suites
  (this session's throttle/route-order/module-schema/interop + pre-existing review/gbxml/analytics/
  discipline/module-config). All are now wired in — the gate runs **86 suites** (was counting 74).
- Verified: 86/86 backend suites, web typecheck + 49 vitest + Pages build + bundle budget all green.

## v0.3.40 — P2: Pydantic module-schema layer (single source of truth for module.json)
- **`module_schema.py`** — a Pydantic `ModuleSchema`/`FieldDef`/`Workflow`/`Transition` layer that
  formalizes what a valid `module.json` is. The config test and the runtime loader now validate against
  the *same* definition: `test_module_config` asserts every shipped module passes it (authoritative,
  fails the build); `load_registry` runs it at startup and logs a warning for a malformed module rather
  than crashing (advisory). New `test_module_schema` proves the layer catches each misconfig class
  (dup fields, unknown types, select-without-options, bad reference target, bad title_field /
  list_column / workflow state / transition / requires) and stays quiet on valid input.
- **Record value validation** (`validate_record`) at create/update: rejects a non-numeric value in a
  numeric field (`number`/`currency`/`percent`) with a 422 before it can land in the JSON `data` blob.
  Select `options` are treated as *suggestions*, not a closed enum (the system routinely stores
  free-form values a picklist didn't anticipate), so membership is deliberately not enforced.
- Fixed the `party` transition key to accept a bare string as well as a list (matches
  `rbac.party_allowed`), and corrected the module-authoring guide's workflow example (`action`, not
  `label`; `party`; convention-based due dates; derived terminal states).

## v0.3.39 — P1: don't block the event loop on heavy IFC/convert/AI work
- **Async offload of blocking work** (P1 from the review). Several `async` endpoints ran CPU/network-
  bound work directly on the event loop, stalling *every* other request on that worker for its whole
  duration. Each now runs in a threadpool (`run_in_threadpool`):
  - `POST …/validate` — `ifcopenshell.open` + IDS validation (seconds+).
  - `POST /convert` — the APS RVT→IFC `subprocess.run` (up to a 30-minute block!) and the E57
    point-cloud decode.
  - `POST /convert/citygml` — CityGML XML parse.
  - `POST …/review/{contract,scope,ask}` — server-side PDF text extraction and the LLM calls.
- **Model load progress** was already real (streamed % + MB with a graceful fallback when the server
  sends no `Content-Length`) — verified, no change needed.

## v0.3.38 — P0 hardening: SQL aggregates, SSRF guard, per-endpoint throttle, bounded property cache
Quick, safe, high-value fixes from the code/UX/perf/security review (Cesium globe deferred — the
recommendation is to adopt the OGC **3D Tiles** format into the existing three.js viewer if geospatial
demand arises, not build a bespoke globe).
- **Performance — SQL aggregates over full-table Python scans.** `due_feed` now filters unfinished,
  soon-due records in SQL (JSON due-date `< horizon` + state `not in` terminal) instead of loading
  every module row + JSON blob; `project_pins` prunes un-anchored rows in SQL; the construction
  **portfolio** dashboard loads only open/mitigating risks and counts open RFIs with a SQL `COUNT`
  rather than three `limit=1_000_000` full scans per project. (`my_work` was already SQL-filtered.)
- **Security — SSRF guard on the admin-settable Speckle URL.** The Speckle server URL comes from the
  Settings UI (untrusted), so `speckle_bridge` now requires `https://` and refuses hosts that resolve
  to private / loopback / link-local / cloud-metadata addresses before any request — closing an
  internal-network / metadata-probe vector. A self-hosted LAN server can opt back in with
  `SPECKLE_ALLOW_PRIVATE=1`.
- **Security — per-endpoint rate limiting for expensive ops** (`throttle.py`). The AI **review**
  endpoints (LLM per call) and the **convert** endpoints (subprocess / paid APS cloud translation)
  now get an always-on per-caller cap independent of the opt-in global limiter; tune or disable per
  bucket via `AEC_THROTTLE_<BUCKET>_RPM`. The "Test connection" AI probe is bounded to a 10s timeout
  with no retries so it can't hang a worker.
- **Perf/memory — bounded property cache.** The in-process element index (`properties.py`) is now an
  LRU capped at ~16 projects/worker (`AEC_PROPS_CACHE_PROJECTS`); evicted projects reload transparently
  from storage — a busy worker no longer holds every project's full element list forever.
- **UX — discoverable command palette.** Added a visible **🔍 Search ⌘K** button in the header so the
  palette isn't hidden behind a keyboard shortcut. Backend suite + web typecheck green.

## v0.3.37 — Design tokens: theme-aware modal error text
- Modal/error message colors across the Account, Connections, and Settings dialogs now use the
  theme-aware **`--err`** token instead of a hardcoded red, so they read correctly in light mode too
  (completing the v0.3.23 status-token pass). The remaining literal colors are intentionally raw:
  canvas drawing colors (takeoff/markup — canvas can't read CSS variables) and already-tokenized
  `var(--status-*, #fallback)` uses. Web typecheck + production build clean.

## v0.3.36 — Module-config validator + forms/CRUD audit
- **Forms/CRUD audit** across all 85 modules — found + fixed a broken list view: `asset_register`
  listed a `warranty_expiry` column that didn't exist (the field is `warranty_expires`).
- **`test_module_config.py`** now validates every `modules/*/module.json` on each test run and fails the
  build on: duplicate field names, `reference` fields with a missing/non-existent target module,
  `select`/`multiselect` with no options, unknown field types, `title_field` or `list_columns` pointing
  at non-existent fields, and workflow `initial`/transition states or `requires` that reference
  unknown states/fields. Prevents the whole class of config-driven-CRUD misconfig going forward.

## v0.3.35 — Frontend load speed: code-split the secondary workspaces
- **~24% smaller initial shell** — the **Finance (proforma)** and **Drawings** panels are now
  code-split and load on first open instead of shipping in the startup bundle. Initial `index` chunk
  **646 kB → 535 kB (139 → 106 kB gzip)**; proforma (77 kB) + drawings (8.8 kB) are separate chunks.
  The default **Construction/Developer** portal stays eager; the 3D viewer engine (@thatopen, ~6 MB)
  and **Studio** were already lazy. Verified live: Finance + Drawings load on first switch with no
  errors; web typecheck + production build clean.

## v0.3.34 — Security hardening: gate the conversion + interop endpoints
- **Auth gap closed.** `POST /convert` (RVT/DWG/NWC bridge) and `POST /convert/citygml` were reachable
  anonymously — they now require an authenticated identity (`current_user`), and `/convert` + `/interop`
  were added to the RBAC middleware's protected-prefix list (defense-in-depth when `AEC_RBAC=1`).
  Combined with the earlier defusedxml + body-cap hardening, the CityGML endpoint is now auth-gated,
  XXE-safe, and size-bounded.
- Web dependency audit clean (`npm audit --omit=dev`: 0 vulnerabilities); Python dep scan runs in CI.

## v0.3.33 — Discipline quantities: rebar tonnage + MEP runs (C)
- **🔩 Discipline quantities** in the viewer's Exports — a quantity roll-up straight from the IFC:
  **reinforcement tonnage** (from `NetWeight`, or estimated from volume × steel density when bars
  aren't weighed), **MEP linear runs** (duct / pipe / cable metres + segment & fitting counts), and
  **structural element volume**. Backs the rebar-viz / MEP-takeoff use case (Koh · WithRebar).
- New `aec_data.qto.discipline_summary` (reuses the QTO quantity reader + geometry fallback) +
  endpoint `GET /projects/{pid}/quantities/disciplines`. `test_discipline.py` covers weights (modelled
  vs volume-estimated), MEP runs, and structural volume; verified live against a real IFC. Typecheck clean.

## v0.3.32 — gbXML energy-model export (B4)
- **↓ gbXML (energy model)** in the viewer's Exports — exports the model to **Green Building XML** for
  OpenStudio / EnergyPlus / IES / DesignBuilder. Spaces carry **area + volume + occupancy from the real
  IFC geometry**, plus building-level **exterior envelope** surfaces (wall + window opening / roof /
  ground slab) with areas from geometry. Valid gbXML 6.01.
  - Honest scope: a **simplified early-design (shoebox) model** — building-level envelope, not a full
    per-space surface-boundary thermal model (that needs IfcRelSpaceBoundary geometry). It seeds an
    energy tool with the spaces/areas/volumes rather than replacing detailed energy modelling.
  - New `aec_data/gbxml.py` (reuses the space schedule + envelope-area extractors) + endpoint
    `GET /projects/{pid}/exports/model.gbxml`. `test_gbxml.py` validates the structure; verified live
    against a real IFC (72 spaces). Web typecheck clean.

## v0.3.31 — Settings: "Test connection" per integration
- Every integration in **Settings ▸ Integrations & API keys** gets a **Test** button with instant
  ✓/✗ + message, so a non-technical admin knows a key actually works before relying on it:
  - **AI** — validates the Anthropic key with a 1-token call.
  - **Email** — connects + STARTTLS + login (no send).
  - **Speckle** — live GraphQL `serverInfo` connectivity check.
  - **Autodesk APS** — 2-legged OAuth (validates client id/secret).
  - **SSO** — confirms client id/secret are present (full sign-in still completes from the login page).
  - **Licence** — key-format check.
- New `conntest.py` dispatcher + `POST /settings/integrations/test` (admin-only). `test_interop.py`
  covers the dispatcher; suite + web typecheck green.

## v0.3.30 — Settings: add all API keys in the UI (no code/env editing)
- **Speckle** and **Autodesk APS** are now in the **Settings ▸ Integrations & API keys** panel, joining
  AI (Anthropic), Email (SMTP), SSO (Google / Microsoft / Procore), and licensing. A non-technical
  admin pastes keys and hits **Save** — no editing `.env` files or code. Secrets stay **write-only**
  (the catalog reports only whether a key is configured, never the value).
- The Speckle and APS bridges now read config via the settings store (DB-saved UI value wins, else the
  env var), so keys entered in the app take effect immediately — same pattern as the AI key.
- Clarified the admin hint: "add API keys here — no code or config files to edit."
- `test_interop.py` asserts the catalog exposes Speckle/APS with write-only secrets; suite + typecheck green.

## v0.3.29 — Federation alignment report + security hardening
- **Model alignment check** (Coordination) — a lightweight companion to federated clash: do a
  project's discipline models share the same **storey scheme** and **georeferenced origin**? Reads each
  model's storey elevations + IfcMapConversion and flags mismatched storey counts/elevations (different
  datums) and survey-origin offsets — the #1 coordination problem. New endpoint
  `/projects/{pid}/models/alignment` + a "📐 Alignment check" viewer action beside Federated clash.
- **Security hardening** of this session's new upload/parse surfaces:
  - CityGML parsing now uses **defusedxml** → XXE / billion-laughs / external-entity bombs are
    rejected (`EntitiesForbidden`) instead of expanding, so a tiny malicious file can't exhaust memory.
  - The contract/spec review engine caps analysed text (~800k chars) so a huge PDF can't drive the
    regex scan unbounded (the global 1 GB body cap still applies to the upload itself).
  - `pypdf` + `defusedxml` pinned in `requirements.txt`.
- `test_interop.py` extended (XXE bomb → 422, alignment → 409); backend suite + web typecheck green.

## v0.3.28 — Interoperability: Speckle bridge + CityGML site-context import
- **Speckle bridge** (Interoperability) — optional, open-source & self-hostable data exchange with the
  wider AEC ecosystem (Rhino/Grasshopper, Revit, Blender, web). Off unless `SPECKLE_SERVER` +
  `SPECKLE_TOKEN` are set; when on, `status()` verifies live connectivity (GraphQL `serverInfo`).
  IFC/Fragments stay the source of truth. Endpoints `/interop/speckle/status` + `…/send` (the chunked
  object upload runs in your credentialed deployment — it never fabricates a commit).
- **CityGML → GeoJSON site context** (GIS & Site) — import CityGML (the OGC standard behind the 3D City
  Database / Cesium city tiles) via **Open mesh / point cloud / GIS…**; the server extracts building
  footprints (with heights) → GeoJSON that renders in the existing GIS reference layer. Namespace-
  agnostic (CityGML 1.0–3.0), fully offline. Endpoint `/convert/citygml`; `.gml/.citygml` accepted.
- `test_interop.py` (Speckle gating + CityGML parse/422) green; web typecheck clean.

## v0.3.27 — Code-readiness check (Safety & Compliance)
- **🏛 Code-readiness check** in the viewer — does the model carry the *data* a plan review needs?
  A property-level rule engine (not a certified geometric code review) checks: egress door width
  recorded (≥ 0.813 m, IBC 1010.1.1), fire rating on walls (IBC Table 601/602), spaces carry floor
  area (IBC 1004.5) + occupancy classification (IBC 1004), egress stairs modelled (IBC 1011), and
  elements typed/classified. Returns a readiness %, a per-rule table with code references, and a
  one-click **3D highlight of the elements to review**. New endpoint `/elements/code-check`.
- Extends the v0.3.25 Data-QA into rule-based checks (Kestrel-style). Rules target IFC classes,
  try several attribute/pset keys, and check presence or a numeric minimum. `test_analytics.py`
  covers it; web typecheck clean.

## v0.3.26 — Preconstruction intelligence: contract risk review + scope-gap + doc Q&A
- **Risk Review** (new Construction-workspace destination — preconstruction intelligence, inspired by
  the AI pre-con review category). Upload a contract/spec PDF (or paste text) and:
  - **Contract risk review** — flags risky clauses by severity (high/med/low) with rationale + a
    suggested redline: pay-if-paid, no-damage-for-delay, broad indemnity, termination-for-convenience,
    sole discretion, lien waivers, LDs, backcharges, retainage, etc. One click adds a finding to the
    **Risk Register**.
  - **Scope-gap detection** — surfaces ambiguous/missing scope in specs & drawing notes ("by others",
    "N.I.C.", "TBD", "as required", "or equal", "match existing"…).
  - **Ask a document** — answers a question grounded in the uploaded doc with **page citations**.
  - New `review.py` engine + `/projects/{pid}/review/{contract,scope,ask}` endpoints. Uses Claude when
    an Anthropic key is set; otherwise a **deterministic clause/marker library** so it works fully
    offline and never fabricates (only flags language actually present).
- **Risk register depth** — the `risk` module gains **response strategy** (Avoid/Transfer/Mitigate/
  Accept), **trigger / warning signs**, and **contingency (Plan B)** to match risk-register best practice.
- Backend suite green (+ test_review, test_analytics); web typecheck clean.

## v0.3.25 — Thematic "Color by property" + BIM data-QA (built-world analytics)
- **Color by any property.** Generalized the 5D heatmaps into a thematic override: pick any IFC
  attribute (class, storey, type, name) or pset/qto property and the model recolours by value —
  numeric ranges get a blue→red ramp, categorical values distinct hues, with a live legend and an
  "N unset" count. New endpoints `GET /projects/{pid}/elements/facets-list` (the picker) and
  `…/color-by?prop=` (server-side bucketing over the property index — scales to large models).
- **BIM data-QA (completeness).** A validation pass over the property index: for each element,
  which required (Name / IFC class / Storey) and recommended (Type / property sets) attributes are
  present vs missing → a headline compliance %, a per-rule table, a one-click **3D highlight of the
  non-compliant elements**, and a CSV export. Endpoint `GET /projects/{pid}/elements/qa`.
- Inspired by computational-AEC data-viz/asset-data workflows; both reuse the existing viewer
  colorize/selection plumbing. Backend 75/75 + web typecheck green.

## v0.3.24 — Construction ↔ Developer split + role-geared dashboards
- **Workspace split.** The oversized single "Construction" portal is now two role-scoped workspaces
  driven by a new `workspace` tag on every `module.json`: **Construction** (the GC build lifecycle —
  Engineering, Preconstruction, Field, Cost, Change Management, Quality, Contracts, Safety, Closeout,
  BIM, Schedule, Resources, Sustainability) and **Developer** (real estate — **Feasibility** `zoning`,
  **Market & Sales** `comparable`/`listing`, **Capital** `investor`, **Operations** `lease`, plus the
  proforma via a one-click **Underwriting →**). A **Show all modules** toggle keeps every register one
  click away for every role — everyone still has access to all data.
- **Role-geared dashboards.** The Developer workspace opens on a real-estate command center (deal
  returns · listings · comps · capital · leases · feasibility) instead of the GC KPIs. The GC
  dashboard now orders its KPI cards by role: the **superintendent** leads with the field
  (punchlist/safety/quality), the **project manager** with controls (RFIs/COs/overdue). Same cards,
  role-appropriate emphasis.
- **Top header.** The role picker is now labeled **👤 Viewing as** and grouped by function
  (Real estate · Construction office · Construction field · Design), set off with a divider.
- **Deeper registers.** `comparable` rebuilt into a full appraisal-grade sales/rent comparison grid
  (comp type, $/unit, NOI, GBA, units, land area, year built, occupancy, condition, distance to
  subject, net adjustment, adjusted price, source + a recorded→verified→excluded workflow);
  `investor` gains ownership %, preferred return %, and commit date. Backend 74/74 + web typecheck green.

## v0.3.23 — Design tokens: theme-aware status colors
- Extracted the hardcoded traffic-light status colors (green/amber/red — 43 occurrences across the
  portal dashboard + proforma) into CSS variables (`--status-good/warn/crit`, `--err`) defined for
  both dark and light themes. Previously the dark-mode hexes bled into light mode; now status colors
  adapt to the theme and there's a single place to tune them. Web typecheck + 49 tests green.

## v0.3.22 — Speed: rollup fields filter in SQL (no more full-table scan per read)
- **Rollup fields** (e.g. a cost code's committed/budgeted/direct totals, a COR's PCO sum) previously
  loaded *every* source-module record for the project and matched the reference in Python on each
  `get_record` — O(N) per rollup, amplified by rollup-heavy dashboards. Now the reference match runs
  **in SQL** via portable JSON extraction (Postgres `->>` / SQLite `json_extract`), so only the
  matching rows are fetched. Same values, far less data scanned/shipped as record counts grow.
  Backend 74/74 (rollup-exercising tests unchanged).

## v0.3.21 — Forms/CRUD accuracy pass (field types, required flags, itemized costs)
- Audited all ~80 module forms against construction best practice and fixed the concrete, verified
  issues:
  - **Currency types**: material/equipment/labor unit rates and `budget.budget` / `budget.forecast`
    were plain numbers — now `currency` (proper `$` formatting, consistent with the rest of the budget).
  - **Required flags** where the field is genuinely mandatory: `submittal.type`,
    `inspection.inspection_type`, `ncr.disposition` — the form now blocks submit + the API validates.
  - **Itemized change-order cost breakdown**: `cor` gains Labor / Material / Equipment / Overhead &
    profit currency fields backing the total (standard COR format).
  - **Process fields**: `permit.applied_date` (processing time), `incident.reported_date` (OSHA
    reporting window), `daily_report.crew_by_trade` (manpower breakdown).
- Demo seed + test updated to supply the newly-required fields. Backend 74/74; web typecheck + 49
  tests green. (Riskier dedup/reference-type findings from the audit are deferred pending consumer
  analysis.)

## v0.3.20 — Command palette (⌘K / Ctrl-K)
- A global **command palette** (Cmd/Ctrl-K from anywhere) — the fast way to reach any workspace,
  module, action, or record without hunting through menus. Fuzzy-ranked, keyboard-first (↑/↓, Enter,
  Esc), with live **record search** (matches ref/title/data via the search endpoint) appended as you
  type. Commands cover the 5 workspaces, shell actions (new project, open IFC/mesh, Report Center,
  save, help), and every construction module (jump straight to its register). First of the Tier-1
  UX-2.0 upgrades from the audit; new `ui/palette.ts` + `PortalUI` open-by-key/record hooks.
- Verified live: opens on Ctrl-K, "fin"→Finance ranks first, Enter navigates; no console errors.
  Web typecheck + 49 tests green.

## v0.3.19 — Fix: attachment images / thumbnails not loading (route collision + COEP/CORP)
- **Portal record images now load.** Three compounding bugs, found by driving the app + reading
  network traces:
  1. **Route collision** — bim.py's `GET /attachments/{id}/download` (the `Attachment` table,
     registered first) shadowed the module-record handler (`RecordAttachment` table), so every
     module attachment 404'd. Moved module attachments to a distinct `/module-attachments/{id}/download`.
  2. **Bad auth gate** — that handler used `require_role("viewer")`, which reads the project id from
     the path; with no `pid` in the path FastAPI demanded it as a query param → 422. Now authenticated
     like bim's download: `current_user` + the attachment's own project (+ signed-URL support).
  3. **COEP blocked the `<img>`** — the SPA is cross-origin isolated (`require-corp`, for the viewer's
     SharedArrayBuffer WASM), which blocks cross-origin image subresources without a
     `Cross-Origin-Resource-Policy` header. Added `CORP: cross-origin` to the module-attachment
     download and to `range_response` (so BIM/topic attachments **and** `model.frag` embed cross-origin too).
- Verified live: an uploaded photo renders on the record (decodes, `naturalWidth>0`, no COEP block).
  Backend 74/74 (new `test_attachments`: distinct path 200 + bytes + `inline` + CORP; old path 404s);
  web typecheck + 49 tests green.

## v0.3.18 — Security: fix stored XSS in portal record rendering
- **Stored-XSS fix (high severity)**: record list cells, the record-detail title/fields, the
  cross-module search results, action-item / due / notification feeds, and the portfolio table all
  rendered user-entered values (titles, field data, project names) via `innerHTML` without escaping —
  a malicious record title like `<img src=x onerror=…>` executed for every user who viewed it. List
  cells now use `textContent`; every remaining `innerHTML` interpolation of record/user data is passed
  through `escapeHtml()`. Verified live: a hostile-title RFI renders as literal text on both the list
  and detail pages, injects no elements, and does not execute. (Found in a full-codebase UI/UX audit.)
- Web typecheck + 49 tests green.

## v0.3.17 — Saved-search alerts + Postgres full-text search
- **Saved-search alerts**: every saved view now tracks a `last_seen_at`, and the portal home shows a
  **🔔 Saved searches with new matches** band — each saved view with its **new-since-you-last-opened**
  count (a never-opened view counts all matches as new). Click a chip to open that filtered list; it
  clears the count. New `GET /projects/{pid}/views/alerts` + `POST …/views/{vid}/seen` + a
  `count_records` engine helper. Opening a view from the dropdown also marks it seen.
- **Postgres full-text search**: cross-module + in-module search is now **dialect-aware** — on Postgres
  it uses `to_tsvector` + a safe **prefix `to_tsquery`** (`conc beam` → `conc:* & beam:*`, so partial
  words and multi-term queries match) ranked by **`ts_rank`**; SQLite (dev) keeps the substring-LIKE
  fallback. No new service (per the earlier no-Elasticsearch decision) and no schema change — the FTS
  is a query-time expression. (For very large prod tables, a GIN index on the tsvector is the natural
  follow-up.)
- Additive migration adds `saved_views.last_seen_at` on startup (nullable ADD COLUMN). Backend 73/73
  (new `test_search_alerts`: alert lifecycle + prefix-tsquery builder + SQLite search); Postgres FTS
  SQL compile-verified (`to_tsvector @@ to_tsquery` + `ts_rank`); web typecheck + 49 tests green.

## v0.3.16 — Bulk-action pickers replace raw prompts (data-entry polish)
- The list bulk-action bar no longer uses `prompt()` for **Assign** / **Transition**: Transition is
  now a dropdown of the module's valid workflow actions + Apply, and Assign is an inline input + Apply
  (Delete stays behind a confirm). Faster, less error-prone bulk edits on a selection — the last
  rough edge from the CRUD/UX audit. Web typecheck + 49 tests green.

## v0.3.15 — Paginated module lists (large registers stay snappy)
- Module list views now **page** the records (100/page) with **‹ Prev / Next ›** controls and a
  position indicator, instead of fetching and rendering every record at once. A register with
  thousands of RFIs/issues/cost codes no longer stalls the browser on open; filter/search/state
  changes reset to the first page. Uses the list endpoint's existing `limit`/`offset` (fetches one
  extra row to detect "more"), so no API change — the pager only appears when the list spills past a
  page. Completes the data-entry UX upgrade set (import → validation → search → pagination).
- Backend 72/72 (limit/offset assertions added); web typecheck + 49 tests green.

## v0.3.14 — Data-entry UX upgrade Phases 2–4: form validation, searchable pickers, faster search
- **Form validation (buy-in + clean data)**: create/edit forms now enforce **required fields
  client-side** — offending inputs get outlined, the first is focused, and submit is blocked with a
  clear "Please fill required field(s): …" message instead of a silent server 422. If the server does
  reject (`missing required field(s): …`), the exact fields are parsed out and highlighted; the form
  keeps all entered values.
- **Searchable reference picker (ties everything together at scale)**: a reference field with more
  than 8 options gets a type-to-filter box, so picking e.g. a cost code stays fast when a project has
  hundreds — the "＋ Add new" inline-create still works.
- **Server-side search (easy to access, scalable — no Elasticsearch)**: the module list/search `q`
  filter now runs in **SQL** (`ref`/`title`/`data`-as-text `LIKE`, applied before `LIMIT`) instead of
  loading a page of rows and scanning JSON in Python — so a search returns the right matches across the
  whole module, not just those on the first page, and scales. Portable across SQLite (dev) and
  Postgres (prod); the JSONB/`tsvector` + GIN upgrade is a clean future step on the same query.
- Backend 72/72 (search assertions added to `test_imports`); web typecheck + 49 tests + Pages build green.

## v0.3.13 — Generic Excel / CSV import for any module (Phase 1 of the data-entry UX upgrade)
- **The #1 data-entry / adoption lever**: every module now has an **⤓ Import** button that bulk-loads
  records from an Excel (.xlsx) or CSV file. New `imports.py` + endpoints
  (`/modules/{key}/import/preview`, `/modules/{key}/import`, `/modules/{key}/import-template.csv`).
- **Two-step, mapping-driven UX**: pick a file → the server sniffs the header row and **auto-maps
  columns to fields** by name/label → a mapping screen lets you adjust each column (or skip), warns
  about unmapped required fields, and shows a sample → import. Type coercion (currency `$1,250` →
  1250.5, dates → ISO, multi-select split); rollup/computed fields excluded. A **blank template**
  download seeds the right headers.
- **Robust + safe**: required-field validation per row (a bad row is reported, never aborts the
  batch), 10k-row import cap, editor-gated + audit-logged. Answers "how do I create a new cost code" —
  the ＋ New form, the inline "＋ Add new" on a reference field, or now a spreadsheet import.
- Verified live: 3 cost codes imported from a CSV via the mapping UI, no console errors. Backend
  72/72 (new `test_imports`); web typecheck + 49 tests green.
- Decision (researched): **no Elasticsearch** — a self-hosted/offline app on Postgres should use
  built-in full-text search; a portable search upgrade lands in a follow-up phase.

## v0.3.12 — UI/UX + security pass over recently-added features
- Consolidated review of four features (site feasibility, feasibility scenario compare, clash-report
  import, BCF viewpoint fidelity).
- **Security**: hardened the clash-report XLSX import against oversized sheets — caps imported issues
  at 5,000 rows and scanned rows at 200,000 (surfacing a `truncated` flag), on top of the existing
  request body-size limit; `read_only` streaming keeps memory bounded. Audited RBAC on every new
  endpoint (feasibility / compare → viewer; clash import → editor + audit log) and confirmed the BCF
  XML parse path uses stdlib ElementTree (no external-entity expansion → not XXE-exploitable).
- **UI/UX**: verified all three new Report-Center tool launchers render and function live against a
  real backend (feasibility envelope, scenario ranking with deltas, clash-report file import), with
  graceful empty states and no console errors.

## v0.3.11 — BCF viewpoint fidelity: orthographic cameras + per-element coloring
- BCF viewpoints now round-trip the **full camera**, not just the view point: camera direction
  (derived from position→target when absent), up-vector, and field-of-view for perspective — plus
  **OrthogonalCamera** (view point + direction + up + view-to-world-scale) so section/elevation
  viewpoints from Solibri / ACC / BIMcollab survive the round-trip instead of collapsing to a bare
  point. Shared helpers (`_camera_xml`/`_parse_camera`) used across every export/import path.
- **Per-element coloring** in viewpoints (`<Coloring><Color><Component/>`) now exports and imports —
  the "the clashing beam is red" emphasis state carries through BCF. Imported viewpoints (incl.
  orthographic + coloured) are re-materialised as `Viewpoint` rows, not just the pin anchor.
- Viewer `captureViewpoint()` now records the projection (perspective/orthographic) + FOV, and
  `jumpToViewpoint()` restores the projection — shared/presence and saved views recreate the actual
  camera. Closes the fidelity gap flagged in the arsray146/ifc-bcf-viewer review.
- Backend 71/71 (BCF test extended with perspective + orthographic + coloring round-trips and an
  end-to-end orthographic-camera import); web typecheck + 49 tests green.

## v0.3.10 — Feasibility scenario comparison (test schemes side by side)
- **New `GET /projects/{pid}/feasibility/compare`** + `feasibility.compare()`: rank every zoning
  scheme (one `zoning` record = one scheme, e.g. "Scheme A · FAR 6" vs "Scheme B · FAR 8") by
  buildable yield — units then GFA — with the binding constraint and Δ-units / Δ-GFA vs. the top
  scheme. The Giraffe-style "test 20 scenarios in the time others analyze one," on the feasibility
  engine shipped in v0.3.8.
- `api.feasibilityCompare()` client + a "▟ Compare feasibility scenarios" tool launcher.
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.9 — Import Solibri / Navisworks clash reports (XLSX → coordination issues)
- **New `clash_import.py` + `POST /projects/{pid}/coordination/import-xlsx`**: drop in a Solibri or
  Navisworks (or any tabular) clash/coordination report `.xlsx` and each row becomes a tracked
  **coordination issue** — which already round-trips to BCF and drops a model pin. GCs receive these
  reports constantly from the BIM coordinator; this turns the spreadsheet into model-anchored issues
  with no re-keying.
- Tolerant parser: sniffs the header row (skips title/preamble rows), maps a wide set of column
  aliases (Solibri Name/Description/Severity/Ruleset/Component-GUID/Location; Navisworks
  Clash-Name/Status/Grid-Location/Item 1/Item 2) by best whole-word match, maps severity → priority
  (Critical/High/Medium/Low), and extracts IFC GlobalIds from one or more component columns into
  `element_guids` so issues anchor on the model.
- `api.importClashXlsx()` client + an "⤓ Import clash report" tool launcher. Inspired by the
  arsray146/ifc-bcf-viewer + addd.io reviews (Solibri/QA-report ingest).
- Backend 71/71; web typecheck + 49 tests green.

## v0.3.8 — Site feasibility / zoning envelope (Giraffe-style) + live-demo fix
- **Fixed the broken live demo**: `massing.build/app/` was 404'ing — GitHub Pages had been switched to
  the legacy branch source (`/docs`), which serves the landing page but not the viewer and conflicts
  with the `pages.yml` Actions deploy. Restored Pages to the "GitHub Actions" source so `/app/`
  deploys again; regenerated the demo snapshot.
- **New `zoning` module + `feasibility.py` engine + `GET /projects/{pid}/feasibility`**: a site
  feasibility / zoning-envelope study (the "Massing" feasibility tool, inspired by Giraffe). From site
  area + zoning controls (FAR, height, floor-to-floor, lot coverage, setbacks, open space, parking,
  unit size) it computes the **maximum buildable GFA as the binding minimum of the FAR cap vs. the
  physical envelope** (footprint × floors), then net buildable area, **unit yield**, parking demand and
  required open space — and **reconciles allowed GFA against the model's actual GFA** (FAR used,
  % of allowed, headroom, over/under) when a source IFC is present.
- New **Site Feasibility / Zoning Envelope** report (Report Center) + a "▟ Site feasibility" tool
  launcher + `api.feasibility()` client method. Demo seeds a zoning record so it's demonstrable.
- Reviewed giraffe.build, synaps.app, addd.io and arsray146/ifc-bcf-viewer; most of their AEC
  capabilities are already covered (clash/BCF, IFC takeoff, dashboards, ask-the-model, reports). Site
  feasibility was the clearest on-brand gap; shipped first.
- Backend 70/70; web typecheck + Pages build green; demo verified live.

## v0.3.7 — Specifications → submittals: spec register, spec-driven submittal log, AI extraction
- New `spec_section` module — the project manual / specification register (CSI MasterFormat section
  number + title, division, the Part 1 "Submittals" article text, Part 2 products, responsible party;
  issued/under-revision/void workflow).
- **Spec-driven submittal log** (`specs.py` + `GET /projects/{pid}/specs/submittal-log`): derives the
  required submittals per spec section from the SectionFormat Part 1 Submittals article (typed via a
  submittal-type classifier — Shop Drawing, Product Data, Sample, Mock-up, Certificate, Test Report,
  Calculations, O&M, Warranty), reconciles them against the submittals actually logged (matched by
  MasterFormat section number), and surfaces **missing submittals** per section with a coverage %.
- **AI/rules submittal extraction** (`ai.extract_submittals` + `POST /specs/extract-submittals`):
  paste spec text → a typed submittal list (Claude when configured, deterministic rules fallback
  offline); `create=true` logs each item as a `submittal` and records the `spec_section`, building the
  log straight from the spec book.
- New **Spec-Driven Submittal Log** report (KPIs, by-type chart, by-section table flagging gaps);
  two tool launchers (spec submittal log; extract submittals from a spec) + client methods.
- Backend 69/69; web typecheck + 49 tests + Pages build green.

## v0.3.6 — Preconstruction depth: decision log, assumptions, VE cycle + alignment dashboard
- New `decision` (cross-stakeholder decision log: rationale, alternatives, cost/schedule impact,
  Aligned/Pending/Disputed) and `assumption` (assumptions & clarifications register with allowance
  exposure) modules. `precon.py` rollups + `GET /precon/decisions` and `/precon/assumptions`:
  open counts, disputed, open cost & schedule exposure, by category.
- **VE cycle** analytics on the existing `value_engineering` module — `GET /precon/ve?target=`:
  proposed/accepted/rejected savings + gap-to-close against an over-budget target.
- **Calibrate-style alignment dashboard** — `GET /precon/alignment`: per-domain RAG (estimate vs budget,
  VE coverage of the gap, decisions, assumptions) + an alignment score. New reports: Decision Log,
  Assumptions & Clarifications, Preconstruction Alignment; tool launchers + client methods.
- Completes the preconstruction-depth parity vs Concntric (estimate continuity + decisions + assumptions
  + VE + alignment). Backend 68/68; typecheck + build green.

## v0.3.5 — Preconstruction estimate continuity (Concntric-style design-phase cost tracking)
- New `estimate_set` module (snapshot tagged by design **milestone** — Concept/SD/DD/CD/IFC/GMP/Award —
  with total, gross SF, basis, source) + `precon.py` engine + `GET /projects/{pid}/precon/estimate-continuity`:
  per-milestone **$/SF**, **milestone-to-milestone cost drift**, first→latest drift, and the **gap vs the
  project budget/GMP** (over/under). A one-click `POST /precon/snapshot?milestone=` prices the current
  model (IFC takeoff) and saves it as an estimate set.
- An **Estimate Continuity** report (PDF/Excel) + Report Center tool launcher; client `estimateContinuity`
  + `preconSnapshot`. Closes the design-phase cost-tracking gap vs Concntric, built on Massing's existing
  estimate/budget primitives. Backend 68/68.

## v0.3.4 — Optional licence enforcement (off by default)
- Licence entitlements can now be **enforced**, but it's **opt-in and OFF by default** — the app stays
  fully open and a licence is optional (no registration) until the operator sets `MASSING_LICENSE_ENFORCE=1`
  (Settings ▸ Massing licence). In open mode every `allows()/require()` gate is a no-op.
- When enabled, gates bite by tier: **IFC export** (`GET /source.ifc`) needs Commercial+ (402 otherwise),
  and **programmatic publishing via the REST API key** (e.g. the pyRevit bridge) needs Commercial+ —
  while interactive "Open IFC…" by a signed-in user stays free on any plan. `require()/require_export()`
  helpers + `_MIN_TIER` upgrade messaging; `/license` + `/capabilities` report `enforced`.
- Settings shows an **"open mode — licence optional"** status when enforcement is off (no nagging).
  Backend 67/67 (open mode grants all; enabling gates IFC/API by tier and clears on upgrade).

## v0.3.3 — Help surfaces the Revit add-in
- The in-app **"Import from Revit for free"** dialog now leads with the one-click **Massing for Revit**
  pyRevit add-in (Publish to Massing), then the free manual IFC-export path and batch pyRevit export,
  with a direct link to the add-in. The docs guide FAQ ("Do I need Revit?") lists the same three paths.
  Keeps the help current with the v0.3.2 bridge + licensing.

## v0.3.2 — Massing for Revit (free pyRevit bridge)
- New **pyRevit extension** (`integrations/pyrevit/Massing.extension`) — a free, open **Revit → Massing**
  bridge that needs no paid Autodesk APS bridge. A **Massing** tab with **Publish to Massing** (exports
  the active model to IFC via Revit's built-in exporter, uploads it, runs the server-side Fragments
  conversion, opens the web viewer), **Open in Massing**, **Sync Issues (BCF)** (RFI/clash/punch
  round-trip over BCF, keyed by IFC GlobalId), and **Settings**.
- `lib/massing_api.py` — a std-lib REST client (works on pyRevit's IronPython 2.7 + CPython 3 engines,
  no `requests`): find/create project → upload `source-ifc` → poll `publish/status` → BCF in/out.
  Covered by `test_revit_bridge.py` (67/67). Built on the LearnRevitAPI StarterKit conventions; uses
  the REST API, so it's a Commercial-plan (and up) path while manual IFC export stays free on any plan.

## v0.3.1 — Massing licensing in Settings
- New `licensing.py` engine + `GET /license`: records the workspace's **Massing licence key**
  (`MASS-XXXX-XXXX-XXXX-XXXX`) and **plan tier** (Free · Home · Commercial · Enterprise) and exposes the
  per-tier feature entitlements (export formats, REST API, SSO, Navisworks) per massing.cloud/docs.
- **Settings** gains a "Massing licence" group (paste key + set plan) and a licence-status line showing
  the active plan, masked key, what it unlocks, and a link to manage at massing.cloud. The key format is
  validated on save (malformed keys / unknown plans are rejected); the key is **masked and never echoed
  back**. `/capabilities` now reports `license_tier`. Backend 66/66.

## v0.3.0 — Massing milestone (analytics + RE/capital depth, hardened, rebranded)
First minor release on the Massing brand — marks a coherent, production-ready milestone after the
0.2.x line: the full **construction-analytics suite** (quality · RFI · submittal · T&M · field-log ·
OSHA safety · closeout) stitched into an executive **project-health rollup**; **real-estate / capital
depth** (lease management, equity-waterfall distributions, investor-portal signed statements, comps
import, WPRealWise/MLS syndication); **production hardening** (non-root API container, `/metrics`,
empty-project + malformed-input regression tests); and the **Massing rebrand** end-to-end. All verified
live in the browser. Backend 65/65; web typecheck + vitest (49) + Pages build green; `npm audit` clean.
- Polish: Excel-export buttons alongside the PDF ones on the rent-roll and cap-table Finance cards
  (backend already served `.xlsx`); optimized the social `og-image.png` (674 KB → 94 KB, palette PNG).

## v0.2.16 — Rebrand to Massing (massing.build)
- Renamed the product from "AEC BIM Platform / ModelMaker" to **Massing** across the app, docs, and
  packaging: window title + PWA name, README/CHANGELOG/SECURITY/guide/roadmap/capability-matrix, the
  Pages landing page (canonical + OG → massing.build), and backend report/branding strings.
- New brand assets — Massing isometric-massing logo + icon (`favicon.svg` / `icon.svg`, header logo,
  landing hero, `docs/img/massing-*`).
- GitHub repo renamed to **ibuilder/massing**; GitHub Pages now serves at **massing.build** (CNAME),
  with `VITE_BASE` switched to root `/app/`. Desktop bundle identifier kept (`com.ibuilder.aecbim`) so
  existing installs keep auto-updating; the updater endpoint follows the renamed repo.
- No functional change — backend 65/65, web typecheck + build green; verified live (title/header/favicon).

## v0.2.15 — Wrap-up: reachability, docs & GitHub refresh
- UI reachability audit of the whole v0.2.x arc — all new features confirmed reachable; closed the one
  gap by folding the **T&M-by-change-event** breakdown into the T&M rollup tool (was PDF-only).
- Docs refreshed to current: README "Recent platform work" now leads with the construction-analytics
  suite + RE/capital depth + production hardening; `SECURITY.md` documents the second signed-anonymous
  surface (investor `statement.public.pdf`) and the non-root API container; GitHub About updated.
- Verified green: backend 65/65, web typecheck + vitest (49) + Pages build, `npm audit` 0 vulnerabilities.

## v0.2.14 — Production hardening: non-root API container + observability test
- The API image now runs as a **non-root user** (`appuser`, uid 10001) — `/app` and the `ifc-data`
  volume path are chowned before mount so the named volume inherits writable ownership; added a
  container-level `HEALTHCHECK` for bare `docker run` (compose already health-gates the stack).
- New `test_metrics.py` (65 suites) locks the `/metrics` Prometheus surface: text exposition with
  `http_requests_total` + latency summary + in-flight gauge + uptime, counted by route template and
  incrementing across requests.
- Closes the production/ops phase — backup/restore runbook, `/metrics`, full healthchecks +
  depends-on conditions, rate-limit env knobs, and the Caddy HTTPS overlay were already in place.

## v0.2.13 — Polish & harden: empty-project robustness + a11y
- New `test_empty_project.py` (64 suites): every analytics / RE surface (14 endpoints + 13 PDF/XLSX
  reports) must return 200 with a sane zeroed structure on a brand-new project — guards the "no data
  yet" path against 500s and blank crashes.
- **Hardened** the equity-waterfall scenario: with no investors in the cap table it now returns a clean
  zeroed result + an explanatory note instead of phantom LP/GP splits; the UI surfaces the note.
- Accessibility: `aria-label`s on the new Finance inputs (capital-call amount, waterfall exit/years,
  comparables CSV textarea + file upload).

## v0.2.12 — Comparables import automation (CSV / RESO) — completes RE/capital depth
- New `comps.py` + `POST /projects/{pid}/comparables/import`: bulk-load comparables from **CSV**
  (`{csv}`) or a **RESO array** (`{reso|rows}`) into the `comparable` module, feeding the
  sales-comparison appraisal. Forgiving header mapping (case/space/underscore-insensitive; accepts
  human headers *and* RESO field names like `UnparsedAddress`/`ClosePrice`/`ClosePricePerSquareFoot`);
  coerces `$1,250,000`/`5.5%`; rows without an address are skipped.
- Appraisal tab: an **Import comparables** card (paste CSV or upload a file → recomputes the sales
  approach); client `importComparables`. Backend 63/63.
- **Milestone:** completes the real-estate / capital depth phase (syndication bridge, lease management,
  equity-waterfall scenarios, investor-portal sharing, comps import). Next: polish & harden, then production/ops.

## v0.2.11 — Investor-portal document sharing (signed statement links)
- `POST /projects/{pid}/investors/{iid}/share` mints a signed, expiring (default 30-day) link to an
  investor's capital-account statement, and `GET …/statement.public.pdf` serves it behind HMAC sig
  verification — the investor opens their statement with **no login** (the private analog of the public
  listing). Forged/absent signatures → 403; reuses `signing.py`, so the RBAC posture is unchanged.
- Finance ▸ Investors: a **🔗** button per cap-table row mints the link and shows a QR/share modal;
  client `shareInvestorStatement`. Backend 63/63 (signed link passes, forged/absent → 403).

## v0.2.10 — Equity-waterfall distribution scenarios (cap-table-tied)
- New `distwaterfall.py` + `POST /projects/{pid}/waterfall`: model a distribution / exit through the
  equity waterfall (preferred return → return of capital → IRR-hurdle **promote tiers**, reusing the
  proforma `run_waterfall`), then **allocate each side's take pro-rata across the actual investor
  records** by commitment. Body: `{exit_amount, contribution_date, exit_date}` or `{distributable[],
  dates[]}`; pref/tiers/style default from the latest proforma scenario, overridable. Returns LP/GP
  totals, IRR & equity multiple, period splits, and the per-investor allocation.
- Finance ▸ Investors gains a **Distribution waterfall (scenario)** card (exit $ + years → LP/GP +
  per-investor); client `waterfallScenario`. Backend 63/63 (waterfall clears to the exit, GP earns
  promote, LP split 2:1 by commitment).

## v0.2.9 — Lease-management depth (renewals · escalations · CAM recovery)
- New `leasemgmt.py` + `GET /projects/{pid}/leases/management`: the **renewal/expiration pipeline**
  (leases expiring ≤90/180/365 days, holdover, options outstanding, rent-at-risk), a forward
  **rent-escalation schedule** (each active lease compounded by its `escalation_pct`, plus the
  portfolio base-rent curve by year), and **CAM / expense-recovery reconciliation** (recoverable
  income = `recovery_psf × rentable_sf` for NNN/recovery leases; pass `?recoverable_opex=` for the
  recovery ratio + over/under-recovery gap).
- A **Lease Management** report (PDF/Excel) + a lease-management card under Finance ▸ Operations
  (expiry buckets, escalation step, CAM recovery); client `leaseManagement`. Backend 63/63.

## v0.2.8 — Real-estate Phase 4: WPRealWise / MLS listing syndication + marketing flyer
- New `re_bridge.py` — a feature-flagged outbound syndication bridge (off unless `REALWISE_URL` +
  `REALWISE_API_KEY` set), mirroring the APS / e-sign bridges. `GET /re-syndication/status` reports
  config; `POST /projects/{pid}/listings/{lid}/syndicate` serializes the listing via `marketing.to_reso()`
  and **upserts it into WPRealWise** (`/wp-json/realwise/v1/listings`, Bearer auth, keyed by `ListingKey`
  so re-pushes update not duplicate). Unconfigured → actionable 422; the RESO export endpoint still works.
- Disposition tab gains **⤴ Syndicate to WPRealWise** (bridge-aware) and a **Marketing Flyer** report
  (`marketing_flyer`, PDF/Excel) alongside the fact sheet. Client `reSyndicationStatus` + `syndicateListing`.
- This completes Phase 4 of docs/realestate-marketing.md (the only deferred real-estate item). `.env.example`
  documents the bridge. Backend 63/63 (test_marketing extended: gate-off 422 + stubbed push asserts
  RESO + ListingKey + Bearer); typecheck + vitest (49) + build green.

## v0.2.7 — Field-capture depth (GPS geotag, offline-queue review, PWA shortcut)
- Field capture now **geotags** records: a "📍 Tag GPS location" one-shot fix stores `gps_lat`/`gps_lon`/
  `gps_accuracy_m` on the captured record (online + queued offline).
- New **offline-queue review** sheet: list pending captures (photo/note + geotag), **Sync now**, or
  discard individual items — reachable from the capture sheet (shown when the queue is non-empty).
- **PWA app shortcut** "Field capture" (manifest `shortcuts`) + a `?capture=1` deep link that opens the
  capture sheet on load — long-press the installed icon to snap a jobsite photo in one tap.

## v0.2.6 — Opt-in self-hosted basemap tiles (GIS)
- New `gis.loadBasemap` + **Open → "Add basemap (self-hosted tiles)…"**: lays a Web-Mercator XYZ raster
  tile grid on the ground as a georeferenced reference overlay (focus lat/lon + zoom; tiles placed at
  their projected metric positions, North → −Z). Lists in the federation panel (align ⛭ / remove) via a
  new `viewer.addReferenceObject`.
- **Offline-first / honors CLAUDE.md:** nothing loads unless the operator supplies a tile-URL template
  (e.g. their own/self-hosted `https://tiles.internal/{z}/{x}/{y}.png`) — no public CDN default.

## v0.2.5 — E57 point-cloud import (server-side, optional pye57)
- New `e57.py` + `POST /convert` (`.e57`) / `GET /convert/e57/status`: converts E57 laser-scan files
  to a decimated `.xyz` (x y z [r g b], capped at 2M points) **server-side**, since there is no viable
  in-browser E57 parser. Optional, dependency-flagged on `pye57` (heavy/native, not a default dep) — the
  status/gate is testable without it and the convert returns an actionable 503 until `pip install pye57`.
- The viewer's **Open mesh / point cloud / GIS…** now accepts `.e57`: it routes the file through the
  converter and loads the resulting point cloud as a reference overlay (federation list, align, remove).
  Clients `e57Status`, `convertE57`. Backend 63/63.

## v0.2.4 — Live e-signature bridge (DocuSeal, self-hosted OSS)
- The feature-flagged 3rd-party e-signature bridge (`esign_bridge.py`) now **implements DocuSeal
  end-to-end** over its REST API (stdlib `urllib`, no SDK): create a template from the rendered PDF →
  open a submission with the signers → return submission id + per-signer signing URLs.
- New `POST /projects/{pid}/contracts/{key}/{rid}/send-for-signature` (renders the doc, routes it,
  stores `data.esign_submission`, audited) + a **"Send for signature"** action in the contract record
  tools; `POST /esign/webhook` reflects provider completion. `GET /esign/status` now reports whether the
  configured provider is `implemented`. Off unless `ESIGN_PROVIDER=docuseal` + `ESIGN_API_KEY`/`ESIGN_BASE_URL`.
- Clients `esignStatus`, `sendForSignature`; transport is monkeypatchable + unit-tested (gating 409,
  template+submission shaping, stored submission, webhook parse). Other providers keep an actionable
  stub. Backend 62/62.

## v0.2.3 — Change-order log + meeting action-item tracker (analytics suite rounded out)
- New `changeorders.py` + `GET /projects/{pid}/change-orders/log`: the **CO value pipeline**
  (pending / approved / executed / rejected), reason mix, schedule-day exposure, ball-in-court, plus
  the upstream **change-event ROM exposure** (potential cost not yet a CO).
- New `actions.py` + `GET /projects/{pid}/action-items/tracker`: **action items** open / overdue /
  by assignee & priority, completion %, and the **meeting log** (by type, last meeting).
- Two new reports — **Change-Order Log** and **Meeting Action-Item Tracker** (PDF/Excel) — plus tool
  launchers; clients `coLog`, `actionTracker`. Backend 62/62.

## v0.2.2 — Executive health banner on the GC dashboard
- The GC dashboard now leads with a **project-health banner** driven by `GET /projects/{pid}/health`:
  a 0–100 score, overall green/amber/red, open/overdue totals, a per-domain RAG chip strip (hover for
  each domain's headline), and the top ranked attention items — the executive rollup surfaced
  first-class instead of only in a tool modal.

## v0.2.1 — Closeout dashboard + project-health executive rollup
- New `closeout.py` engine + `GET /projects/{pid}/closeout/summary`: **punchlist completion &
  ball-in-court** (open=Subcontractor, ready=GC-verify, verified; % complete, overdue, open-cost,
  by trade/priority), **commissioning pass rate** (by result & test type), **completion certificates**,
  **warranty expirations** (active / expiring-90d / expired), and **O&M-manual turnover** (% accepted).
- New `projecthealth.py` engine + `GET /projects/{pid}/health`: an **executive rollup** that stitches
  the seven analytics domains (RFIs, submittals, quality, safety, T&M, field reporting, closeout) into
  per-domain green/amber/red status, an overall 0–100 health score, open/overdue totals, and a ranked
  list of attention items.
- Two new Report-Center reports — **Closeout Dashboard** and **Project Health (Executive)** (PDF/Excel) —
  plus "Project health" (top of tools) and "Closeout dashboard" launchers; clients `projectHealth`,
  `closeoutSummary`. Verified live over HTTP against the preview DB (endpoints + all 6 new PDFs). Backend 62/62.

## v0.2.0 — Safety dashboard (OSHA TRIR / DART) + construction analytics suite complete
- New `safety.py` engine + `GET /projects/{pid}/safety/summary`: **OSHA incident rates** — TRIR,
  DART, LTIFR, and severity rate on the 200,000-hour base, computed from the incident module's
  classification / osha_recordable / lost-days / restricted-days fields. Worker-hours are taken from
  `?hours=`, else estimated from daily-report manpower (man-days × 8h). Also rolls up the
  **safety-observation leading-indicator mix** (safe vs at-risk, safe:at-risk ratio, close-out %),
  **toolbox-talk coverage** (talks + attendees), and the **safety-violation log** (open / overdue / by severity).
- A **Safety Dashboard (OSHA)** report (PDF/Excel) — distinct from the existing simple Safety/Incident
  Log — plus a "Safety dashboard (OSHA)" tool launcher; client `safetySummary`. Backend 62/62.
- **Milestone:** this completes the construction analytics suite — every core field log (submittals,
  RFIs, T&M, quality, daily reports, safety) now has a first-class rollup, exportable report, and tool launcher.

## v0.1.99 — Field-log rollup (daily reports → manpower / weather / coverage)
- New `dailylog.py` engine + `GET /projects/{pid}/daily-reports/summary`: **manpower trend**
  (total / avg-per-day / peak with date, preferring the manpower_log rollup over the typed count),
  **weather-impact lost-day equivalents** (Minor 0.1 / Half 0.5 / Full & Stoppage 1.0), **delay days**,
  and **reporting coverage** (logged days vs the date span), with by-weather & by-impact breakdowns.
- A **Field-Log Rollup** report (PDF/Excel) in the Report Center + a "Field-log rollup" tool launcher;
  client `fieldLogSummary`. Backend 62/62.

## v0.1.98 — RFI register / log analytics
- New `rfi.py` engine + `GET /projects/{pid}/rfi/register`: **ball-in-court** (draft→GC, open→Consultant,
  answered→GC-accept, closed/void), **overdue** (date-required passed while awaiting a response),
  **response turnaround**, and **cost/schedule-impact exposure**, with by-discipline & by-priority breakdowns.
- An **RFI Register** report (PDF/Excel) in the Report Center + an "RFI register" tool launcher;
  client `rfiRegister`. Backend 62/62.

## v0.1.97 — Quality dashboard (inspections / NCR loop / deficiency ball-in-court)
- New `quality.py` engine + `GET /projects/{pid}/quality/summary`: **inspection pass-rate KPIs**
  (pass rate = pass+conditional / decided, first-pass yield = clean pass / decided, by type & result,
  agency count); the **NCR disposition→corrective-action→close loop** (by state/disposition/severity,
  overdue, undispositioned, avg days-to-close); and the **deficiency ball-in-court rollup**
  (open=Subcontractor, corrected=GC-verify, closed; by trade & severity, overdue).
- A **Quality Dashboard** report (PDF/Excel) in the Report Center + a "Quality dashboard" tool
  launcher; client `qualitySummary`. Backend 62/62.

## v0.1.96 — T&M → change-event tie
- eTickets gain a **change_event** link; `tm.by_change_event` rolls up field T&M by the change event
  it belongs to (`GET /tm-by-change-event`), with linked vs unassigned totals — closing the chain
  field T&M → change event → CO → SOV → AIA billing (G702/G703 already in `cost.py`). The T&M Log
  report gains a "T&M by change event" table. Backend 62/62.

## v0.1.95 — RFI/submittal distribution lists
- RFIs & submittals gain a **Distribution (CC)** field; `distribution.py` resolves it (names or emails,
  comma/semicolon/newline-separated) against the **Contact directory** into recipients + emails.
- `GET /projects/{id}/modules/{key}/{rid}/distribution` returns the resolved list; the resolved emails
  now ride the **record.transition webhook** (`distribution: [...]`) so a listener can notify the CC list.
- Tests in `test_distribution.py` (backend 62/62; rfi/submittal fieldsets kept contiguous).

## v0.1.94 — drawing transmittals + issuance diff
- The drawing-set register now classifies each current sheet as **new** vs **revised** (issuance diff)
  and reports `new_count` / `revised_count`.
- **Drawing transmittal PDF** (`GET /drawing-set/transmittal.pdf?to=…&note=…`): the controlled current
  set grouped by discipline with current revision + New/Revised status, recipients and a note — a ⬇
  Transmittal button in the drawing-set view. Backend 61/61.

## v0.1.93 — construction depth: T&M rollup + submittal register
- **T&M / eTicket cost rollup** (`tm.py`): aggregates eTickets into labor/material/equipment totals,
  by status, with **billed vs unbilled**; `GET /tm-summary` + a T&M / eTicket Log report.
- **Submittal register** (`submittals.py`): spec-section-organized log with **turnaround**
  (received→returned), **ball-in-court**, and **overdue** flags (required-on-site passed, not closed);
  `GET /submittals/register` + a Submittal Register report.
- Both auto-list in the Report Center (PDF/Excel) and have interactive launchers in "Project tools &
  analytics". Tests in `test_construction_depth.py` (backend 61/61).

## v0.1.92 — capital calls & distributions now post to the cap table
- `POST /capital-call` and `/distribution` accept `persist: true` — posting each allocation to the
  investor's **contributed** / **distributed** running total, so the cap table's contributed /
  distributed / unreturned (and the statement PDF) track over time instead of being preview-only.
- Investors tab: **Preview** vs **Record** buttons; recording refreshes the cap table live.
- Backend 60/60 (incl. a persisted-call assertion).

## v0.1.91 — dedicated Operations & Investors tabs + investor statements
- Finance gains two first-class sub-tabs: **Operations** (the hold-phase rent roll — occupancy, WALT,
  in-place income, value-from-rent-roll) and **Investors** (cap table, capital-call/distribution
  tools, per-investor downloads) — moved out of the Valuation tab so each has a clean home.
- **Per-investor capital-account statement PDF** (`GET /projects/{id}/investors/{iid}/statement.pdf`):
  commitment, ownership, contributed/distributed, unreturned + unfunded — a ⬇ per row on the cap table.
- Verified live (both tabs render with seeded data; statement link present); backend 60/60.

## v0.1.90 — accessibility pass: every feature reachable in the UI
A UX audit found seven computed features were API/report-only (no buttons). All are now wired in:
- **Finance ▸ Valuation tab** gains a **Rent roll** card (occupancy/WALT/in-place income + "value
  from rent roll"), an **Investor cap table** card with **capital-call / distribution** tools, and
  the existing appraisal/disposition cards.
- **Report Center ▸ Project tools & analytics** adds launchers for the **Project assistant**,
  **WH-347 certified payroll** (week picker + preview), **Drawing-set register**, **ITB coverage**,
  and **Field-verification coverage**. (The rent_roll/cap_table/appraisal/listing reports already
  auto-list there.)
- **Login** now shows an "SSO available — set `AEC_OAUTH_*`" hint when no providers are configured,
  instead of silently hiding sign-in options.
- Verified live (all surfaces render, console clean), authz re-audited (every new endpoint
  `require_role` + project-scoped; financial writes = editor), `npm audit` 0 vulns, and the new
  tables (`mod_lease`, `mod_investor`, `element_verifications`) confirmed to migrate on **Postgres**.

## v0.1.89 — operate, capital, payroll, drawing-set, assistant & ITB
Six capability gaps closed across operations, capital, payroll, drawing-set control, the project
assistant, and invitation-to-bid.
- **Operating asset mgmt (rent roll):** a `lease` module (Operations) + `rentroll.py` — occupancy,
  WALT, lease-expiration schedule, in-place income; `GET /rent-roll` + a Rent Roll report. The
  appraisal income approach can value off the actual roll: `GET /appraisal?rentroll=1`.
- **Investor / LP capital:** an `investor` module (Capital) + `capital.py` — cap table by commitment,
  pro-rata **capital-call** & **distribution** allocation; `GET /cap-table`, `POST /capital-call`,
  `POST /distribution` + a Cap-Table report. Data-room reuses the document module + attachments.
- **Certified payroll (WH-347):** `payroll.py` aggregates timesheets × labor rates into a weekly
  Davis-Bacon certified-payroll PDF (straight/OT split, prevailing-wage flags); `GET /payroll`,
  `GET /payroll/wh347.pdf`.
- **Drawing-set register:** `drawingset.py` derives the controlled current set from `drawing`
  records (latest revision per sheet = current, earlier = superseded) + sheet index + discipline
  rollup; `GET /drawing-set`.
- **Project assistant:** `assistant.py` extends "ask" from the BIM index to the whole project
  (module tallies, schedule, budget, risk, rent roll); `POST /assistant` (+ `/assistant/snapshot`),
  AI-optional (returns the snapshot without a key).
- **ITB tracking:** `itb.py` rolls up bid packages vs submissions (invited / responded / bonded /
  low bid / coverage gaps); `GET /bidding/itb` + `POST /bidding/packages/{id}/invite`.
- Tests: `test_operate_capital`, `test_payroll_drawings`, `test_assistant_itb` (backend 60/60).

## v0.1.88 — model intelligence, field verification & embeddability
Three features adapted from a scan of **Argyle** (AR field verification) and **Flinker** (OpenBIM in
M365) — built to Massing's open, self-hosted, $0 identity (no AR hardware, no MS-365 lock-in).
- **Ask the model** — `POST /projects/{id}/ask` answers plain-English questions ("how many fire-rated
  doors on L3?", "total curtain-wall area") grounded in a snapshot of the property index (counts by
  class/storey, Psets, facets). Uses the configured AI provider; **degrades to the data snapshot**
  when no key is set. A "✦ Ask" button in the Model workspace.
- **Field verification + install coverage** — mark elements **installed / verified / deviation**
  against design (keyed by GUID, photo-anchored) from the element panel; a coverage summary
  (`GET …/verification/coverage`, % verified/installed of the model total) + a **deviation log** for
  the verified-handover to operations. Argyle's core value, no AR hardware. New `ElementVerification`
  table + `routers/verification.py`.
- **Embeddable viewer + outbound webhooks** — `?embed=1` renders a chrome-less, read-only viewer for
  an `<iframe>` / web-component / Teams tab; module transitions fire **outbound webhooks**
  (`AEC_WEBHOOK_URLS`, fail-open) so Power Automate / Zapier / a custom listener can react. New
  `webhooks.py`.
- Tests: `test_ask.py`, `test_verification.py`, `test_webhooks.py`. Verified live (Ask snapshot,
  embed chrome-less, webhook dispatch + fail-open).

## v0.1.87 — workflow engine upgrades
Cross-cutting upgrades to the config-driven modules engine — each lights up across all ~75 modules,
drawn from construction-management workflow best practice.
- **Transition field-gating** — a workflow transition can declare `requires: [field, …]` that must be
  filled before it fires (RFI can't be *Answered* without an answer). `available_actions` advertises
  it; the action button disables with a "(needs …)" hint until satisfied. Generalizes the attachment
  evidence-gate.
- **Company / Contact directory + first-class lookups** — new `company` + `contact` modules; vendor /
  sub / contact fields become `reference` lookups into the directory (`subcontract.vendor_company`),
  with the picker, resolution and reverse links for free.
- **Due dates / SLA feed** — `GET /projects/{pid}/due-feed` + a "⏰ Deadlines" portal-home widget:
  open records past or near their due date (overdue / due-this-week), across the 11 modules with a
  due field; terminal/closed records excluded.
- **In-app workflow map** — the record view renders a compact state diagram (current state
  highlighted, reachable next-states emphasized). (Saved views already existed.)
- Tests: `test_workflow_gate.py`, `test_due_feed.py`, `test_directory.py` (backend 54 suites).

## v0.1.86 — disposition & valuation (real-estate marketing)
Close the development loop from build to **sell/lease** and **market value** — the two things only a
BIM-native platform can do, because Massing owns the model + proforma. (See
[docs/realestate-marketing.md](docs/realestate-marketing.md).)
- **BIM-native marketing kit** — a config-driven `listing` module (RESO-aligned fields + a workflow
  mirroring RESO `StandardStatus`) that **auto-fills from the project**: areas/unit-mix from the model,
  NOI/cap/asking price from the proforma. One click generates a **Listing Fact Sheet** PDF and a
  signed, expiring **public link + QR** to share a listing without a session (the only anonymous
  surface — token-scoped, read-only, rate-limited).
- **Tri-approach appraisal** — `appraisal.py` fuses the three classic approaches from data already
  in-system: **Cost** (replacement cost from the estimate + land − depreciation), **Income** (NOI ÷
  cap from the proforma), **Sales comparison** (adjusted $/SF from the `comparable` module),
  reconciled into an opinion of value with a range. New **Valuation** tab in Finance (three approach
  cards, editable reconciliation weights, value-by-approach chart) + a **Valuation report** (PDF/Excel).
- **RESO export seam** — `marketing.to_reso()` serializes a listing to RESO Data Dictionary fields, so
  a later bridge can push listings to WPRealWise / an MLS as a serialization, not a rewrite.
- Endpoints: `GET /projects/{pid}/listings/autofill`, `GET|POST /projects/{pid}/appraisal`,
  `GET …/listings/{lid}/reso`, `POST …/listings/{lid}/share`, `GET …/listings/{lid}/public`.
  Tests: `test_appraisal.py` (engine) + `test_marketing.py` (autofill → appraisal → reports → RESO →
  signed public link).

## v0.1.85 — production readiness
- **Readiness probe:** new `GET /ready` (and `/readyz`) pings the DB (`SELECT 1`) and returns `503`
  when it's unreachable, so a load balancer / orchestrator stops routing to a degraded instance;
  `GET /health` (`/healthz`) stays a cheap dependency-free liveness check. The ping runs under a hard
  wall-clock timeout (`AEC_READY_TIMEOUT`, default 3s) and the Postgres engine gets a connect timeout +
  TCP keepalives, so a *black-holed* DB (paused host / partition) yields a prompt `503` instead of
  hanging the probe — verified against a real paused Postgres.
- **Multi-worker login lockout:** the brute-force lockout now shares its counter across workers via
  `AEC_REDIS_URL` (atomic Redis `INCR`+`EXPIRE`), fail-open to the in-process counter — matching the
  per-IP rate limiter. The API runs multi-worker in production, so the lockout now actually holds.
- **Hardened-by-default deploy:** `docker-compose.prod.yml` now sets RBAC, `AEC_REQUIRE_SECRET`,
  HSTS, secure cookie, strict CSP, body cap, rate limit, and ships a `redis` service for the shared
  counters; `.env.example` documents every hardening flag (and how to generate a strong secret).
- **Schema migrations documented + tested:** the app uses an additive, dbDelta-style startup sync
  (fits the config-driven dynamic module tables) rather than Alembic; `SECURITY.md` documents the
  policy + the manual escape hatch for non-additive changes, and `test_migrate.py` proves a new
  nullable model column is ALTERed onto an existing DB and new indexes backfill (additive-only).

## v0.1.84 — security hardening
- **Access control:** RBAC defense-in-depth gate (anonymous blocked from project/finance/admin
  prefixes when `AEC_RBAC=1`), `require_role` on every project-scoped finance/data endpoint, attachment
  download IDOR fixed, projects list scoped to the caller's memberships.
- **Hardening headers** on every response (nosniff, frame DENY, referrer, CSP) + **opt-in strict CSP**
  (`AEC_CSP=1`); **request body-size cap** (`AEC_MAX_UPLOAD_MB` → 413).
- **Path traversal** closed at the storage layer (resolved-path containment) + upload-filename sanitization.
- **Auth:** login brute-force lockout (429), `Secure` auth cookie over HTTPS, fail-fast on a default
  signing secret (`AEC_REQUIRE_SECRET=1`).
- **Signed/expiring download URLs** for `model.frag` + attachments (HMAC, short-lived) — for QR share /
  worker fetch / deep links without a session.
- **Docs:** new `SECURITY.md` (disclosure policy, threat model, production env-flag checklist).
- Production npm dependencies carry no known vulnerabilities (CI runs `pip-audit` + `npm audit`).

## v0.1.83 — charts & graphs (construction + real-estate best practice)
- **Reusable SVG chart kit** (`ui/charts.ts`, dependency-free, theme-aware): multi-series line
  (S-curve), grouped/stacked bar, waterfall, tornado, histogram, donut, progress bar, sparkline.
- **Finance (proforma)** — Underwriting: a **capital-stack donut** (debt/LP/GP), a **JV-distributions
  donut**, equity cash-flow bars, and a one-way **IRR tornado** (derived from the 2-way matrix).
  Statements: **NOI vs net-income** line + **cash-flow-by-year** stacked bar.
- **Construction (GC portal)** — executive **progress bars** (% complete · bought-out · spent) and a
  **budget vs committed vs actual vs EAC** grouped bar by category.
- **Report Center** — charts embedded in the PDFs (cost bar, EVM cash-flow S-curve, financials
  NOI/net-income line) via reportlab's built-in graphics; Excel keeps the data tables for re-charting.

## v0.1.82 — financial statements & tax modeling
- **Three financial statements + tax** — the Finance proforma gains a **Statements** tab (and a
  Report-Center "Financial Statements" PDF/Excel) built on `financials.py`:
  - **Income statement** — stabilized operating P&L (Potential Gross Rent → vacancy/credit → Effective
    Gross Income → operating expenses → **NOI**; then interest, straight-line **depreciation**, income
    tax → **net income**) plus a year-by-year operating summary.
  - **Balance sheet** — Assets (land + improvements net of accumulated depreciation + capitalized
    financing + cash) = Liabilities (loan) + Equity (paid-in + retained); **balances every year**.
  - **Cash-flow statement** — GAAP three-section (Operating / Investing / Financing), indirect method.
  - **Tax** — 27.5-yr residential / 39-yr commercial straight-line (land non-depreciable), annual income
    tax with **passive-loss carryforward** (§469: loss years are suspended, offset later income, and the
    remainder releases against the gain at sale), and at sale **§1250 depreciation recapture** (≤25%)
    stacked on **capital gains** (+ NIIT) — driving an **after-tax** equity IRR / multiple. Institutional
    defaults, overridable via a `tax` block.
  - **Per-year columns** — columnar **balance sheet by year** (balances every column) and **cash flow by
    year** alongside the stabilized-snapshot cards.
  - **Two-sided budget** — the development budget as **Uses** (left) vs **Sources** (right); both tie.
  - Endpoints: `POST /proforma/financials`, `GET /projects/{pid}/financials`,
    `GET /projects/{pid}/budget/two-sided`.

## v0.1.81 — properties panel, multi-city permits, money + BCF hardening
- **Robust properties panel** — the element inspector is now structured (IFC-class badge, copyable GUID,
  collapsible **Attributes / Quantities / Property Sets** with counts), formats values (numbers,
  Yes/No, dashed empties, `{value,unit}`), and adds a live **filter**, per-row click-to-copy, and
  **Copy all**. Quantities (qtos) are shown for the first time; the no-backend fallback renders a
  collapsible tree instead of raw JSON.
- **Interchangeable multi-city permit open data** — a Socrata-based feed (NYC · SF · Chicago · LA ·
  Austin, one-entry to add a city) normalized to one record shape; query near a point/by text, a GeoJSON
  GIS overlay, and a **"Import from city open data"** action that seeds the GC `permit` log
  (source-tagged, deduped). From the github.com/ibuilder portfolio review.
- **Sources & Uses reconciles to the dollar** — line items now sum exactly to the totals and sources tie
  to uses (no per-line rounding drift); `balanced` is a strict check. (WPLedger money-handling review.)
- **BCF round-trip preserves pins** — project-Topic export/import now carry a pin's element GUIDs +
  anchor (previously dropped); 5 orphaned test suites wired into CI; empty/cyclic-project edge cases and
  a 404 (not 500) for unknown modules. Backend suites: 47.
- **Schedule acceleration advisory** — rule-based crash / fast-track / near-critical levers off the CPM
  critical path; `GET /projects/{pid}/schedule/optimize` + an "Accelerate (advisory)" tool. Advisory only.
- **Project risk digest** — cost + schedule + open-items + safety drivers with a prioritized narrative;
  `GET /projects/{pid}/risk-digest` + a Report Center "Risk Digest" report.

### audit follow-ups (ties, queue-readiness, RFI triage, schedule alerts)
- **Predictive schedule alerts** — `GET /projects/{pid}/schedule/alerts` (+ a section in the Executive
  report): overdue work, late / at-risk starts (incomplete predecessor), behind-schedule SPI, and a
  procurement-risk proxy, from the cost-loaded schedule + CPM.
- **AI RFI triage** — categorize + ball-in-court + draft response (see e-sign/AI sections).
- **Relationship ties** — COR ⤳ SOV line, awarded bid ⤳ subcontract conversions; cor→change_event ref.
- **Queue-readiness (no Celery)** — IFC publish extracted to a worker-callable `run_publish(pid)` +
  interrupted-job recovery; rationale in docs/audit-2026-06.md.

### PDF digital signatures (PAdES) + e-sign options
- **Digitally sign (PAdES)** — a contract/CO can be signed with a certificate-based **PAdES** digital
  signature (Bluebeam's model) via **pyHanko**: the document is rendered, signed (tamper-evident,
  self-validating), attached, and the signer + cert **fingerprint** recorded. Uses a self-signed
  platform certificate by default (offline, no cost); set `ESIGN_P12` to sign with your own / a CA cert.
- **3rd-party bridge (feature-flagged)** — `esign_bridge.py` + `GET /esign/status` scope DocuSign /
  Dropbox Sign / self-hosted DocuSeal·Documenso for legally-binding multi-party signing (off until
  `ESIGN_PROVIDER` is configured). Decision write-up in **docs/esign-options.md** (electronic vs
  digital vs SaaS vs OSS; eIDAS / ESIGN Act / UETA; recommendation).

### Report Center (detailed, exportable reports)
- **📊 Report Center** — a catalog of detailed reports, each downloadable as **PDF or Excel**:
  **Executive Summary** (CPI/SPI/EAC, % complete, open RFIs/submittals/COs, safety), **Cost Report**
  (budget/committed/actual/forecast/variance by category), **EVM / S-Curve** (SPI, EAC, cash-flow
  curve), and operational logs (Change Order / RFI / Submittal / Daily / Safety) + **Contracts &
  Signatures**. Built from the existing px / budget / module engines (`reports.py`); endpoints
  `GET /reports` + `GET /projects/{pid}/reports/{report}.{pdf,xlsx}`. Opens from the 📊 toolbar button.

### contract & change-order document lifecycle
- **Generate contract documents** — from a contract record: **Prime Contract**, **Subcontract**
  (AIA A401-style), and **Change Order** (AIA G701-style, showing original → revised contract sum)
  PDFs, merged with project/contract data (`contracts.py`, reportlab).
- **Exhibit generator** — **Compose Exhibit A — Scope of Work** from an editable clause/scope library
  (`scope_library.py`: general/supplementary conditions + per-CSI-division scopes with `{{merge}}`
  tokens); pick clauses → exhibit PDF, attachable to the record.
- **View & markup** — open any generated contract/CO in the PDF markup overlay to redline
  before signing.
- **Signatures & approval** — capture per-party typed signatures (`POST …/contracts/{key}/{rid}/sign`,
  one per party, audited) that render into the document; route/approve via the existing party-gated
  workflow. Endpoints: `GET /scope-library`, `GET …/contracts/{key}/{rid}/document.pdf?doc=&clauses=&attach=`.

### AI estimate (text → BOQ)
- **Draft a Bill of Quantities from a description** — the conceptual-estimate tool gains
  **✨ Draft BOQ from description**: type the scope and the AI returns priced line items
  (description / qty / unit / rate / CSI division) with a rolled-up total. Reuses the existing
  Anthropic provider + `ai_enabled()` gate; degrades to a clean stub (no fabricated numbers) when no
  API key is configured. Endpoint `POST /projects/{pid}/ai/estimate`.

### regional classification standards + GAEB export
- **Regional classifications** — map the model estimate's IFC-class line items to **DIN 276** (DACH),
  **RICS NRM 1** (UK), or **CSI MasterFormat** (US/CA) via `GET /classifications` + a built-in code
  table (`classification.py`).
- **GAEB DA XML (X83) export** — `GET /projects/{pid}/estimate/gaeb.x83?system=…` exports the
  estimate as a GAEB 3.2 Bill of Quantities (the DACH tender standard); the conceptual-estimate
  result now has **↧ GAEB · DIN 276 / NRM 1 / MasterFormat** download buttons.

### PDF takeoff & markup
- **PDF takeoff** — **Drawings → 📄 PDF Takeoff** opens a PDF drawing (pdf.js, offline worker),
  lets you **calibrate the scale** (draw a line, enter its real length), then **measure distance /
  area**, **count** items, and drop **rectangle** annotations directly on the sheet — with a running
  Σ length / area / count panel, an editable measurement list, and **CSV export** of the takeoff
  lines. Coordinates are stored in PDF user-space so measurements stay correct as you zoom.

### GIS / topography layer
- **Import GIS & topography** — **Open ▾ → Open mesh / point cloud / GIS…** now also opens
  **GeoJSON** (parcels, contours, site vectors → points/lines/filled polygons) and **GeoTIFF DEMs**
  (→ a hypsometric terrain mesh displaced by elevation). Layers are georeferenced (lon/lat projected
  to metres; projected coords pass through), list in the federation panel, and align with the same
  ⛭ transform / working-origin as other reference models. Offline (`geotiff` + `earcut`, no CDN).

### model federation, alignment & federated clash
- **Navisworks-style model layering** — each reference overlay (mesh / point cloud) now has a ⛭
  transform panel in the federation list: X/Y/Z offset, a **Z-up → Y-up** flip, uniform scale,
  **Move to picked point**, and Reset — so you can align several models in one space.
- **Multi-discipline models** — append discipline IFCs (STR / MEP / ARCH …) to a project via the
  Coordination panel's **＋ Add discipline IFC** (or `POST /projects/{pid}/models`); they layer in
  the viewer and join clash.
- **Federated (cross-discipline) clash** — **🔗 Federated clash** runs `detect_federated_files`
  across the project's layered models (primary source IFC + appended disciplines), excludes
  intra-model overlaps, lists clashes grouped by model-pair, and turns the top hits into BCF clash
  topics → pins / Issues. (Clash needs real IFC geometry — meshes/point clouds don't clash.)

### multi-format reference models + QR share
- **Open meshes & point clouds** — alongside IFC/Fragments, the viewer now opens **OBJ, STL, PLY,
  glTF/GLB** meshes and **PCD, XYZ, LAS, LAZ** point clouds as **view-only reference overlays** (IFC
  stays the source of truth). LAS/LAZ are decoded locally (offline) via a vendored `laz-perf` WASM;
  big clouds are decimated to stay responsive. Reference models list in the federation panel with
  visibility + remove. **Open ▾ → Open mesh / point cloud…**
- **QR share** — a toolbar **📱 Share via QR** shows a scannable deep link to open the project on a
  phone/tablet.
- **Faster Open IFC** — the native file dialog now appears instantly (the heavy 3D module warms in
  parallel); large IFCs (>~60 MB) route through the server pipeline and stream optimized fragments
  instead of parsing the whole file in-browser.
- **Live demo shows the full platform** — the GitHub Pages viewer-only build now bundles a read-only
  sample project so the GC portal, Budget/GMP, Schedule and Finance panels render with real data.

## v0.1.80 — multi-user persona views + optional paid RVT→IFC bridge
- **Membership shapes the view** — a project member's party role (GC / Owner / Consultant /
  Subcontractor) now auto-selects their persona on open, so they land in the right workspace set;
  capability role already gated edit controls. Members modal (add / role / party / remove) present.
- **Revit (.rvt) → IFC bridge (optional, paid)** — feature-flagged on `APS_CLIENT_ID/SECRET`, doubly
  gated: bridge off → 501 + the free IFC-export path; on → must `confirm_cost` (Autodesk bills per
  conversion). Real RVT→IFC runs Revit's exporter via APS Design Automation (`APS_DA_ACTIVITY`).

## v0.1.79 — 4D colour scrub + quantity takeoff by floor
- **Time-aware 4D scrub** — scrubbing the timeline paints the model green floor-by-floor (rest
  ghosted) with a live **cost-burn** readout from the cost-loaded cash-flow curve.
- **QTO by floor & discipline** — quantities + cost mapped to the storey they sit on, per-floor
  totals + a discipline (IFC class) roll-up.

## v0.1.77–78 — 5D element intelligence
- **Click an element → its 5D** — schedule activity (%-complete, dates, hard-tied vs by-trade) +
  cost-code budget vs committed vs actual. **Model heatmap** — colour by %-complete or cost variance.
- **One-click generate seeds the GC portal** — lot→building→deal also creates cost codes, a
  hard-cost-allocated budget, a GMP prime contract, and a cost-loaded schedule.

## v0.1.73–76 — dashboards + investor deliverables, one language
- **Developer Overview command center** + cross-pillar **Portfolio** (GC status *and* developer
  returns per project, blended IRR), one-click **Save scenario**, and a **Construction Status**
  section in the investor memo + deck. **PX executive band** — on-schedule next to on-budget.

## v0.1.67–72 — developer ↔ GC capital chain
- **GMP ↔ hard-cost reconciliation + one-click sync**, construction **draws** from the schedule, an
  **actuals loop** (owner invoices → re-forecast IRR), **construction-loan draws** (equity-first)
  with **interest accrual** + **per-cost-code composition**, and a **lender draw-request PDF**.

## v0.1.60–66 — GMP project budget (its own destination)
- **Budget** is a first-class destination: the agreed GMP broken to every cost code & bid package +
  General Conditions / Requirements (incl. **staffing** projections) + overhead / fee / contingency,
  each budget vs committed vs actual vs **EAC/ETC**. **Buyout savings**, **change orders → revised
  GMP**, owner **SOV from the budget**, a **cash-flow S-curve**, **baseline + variance** — reconciled
  to the developer proforma's hard cost.

## v0.1.53–59 — relational schedule, field/mobile, GC module depth
- **Relational scheduling** — `schedule_activity` drives the Gantt / Line-of-Balance / CPM **and**
  the 3D 4D model; editable P6 `.xer` import; **lookahead** + **milestone** schedules.
- **Field/mobile** — bulk photo + camera capture, photo-first records, offline upload queue;
  **coordination-issue BCF round-trip**.
- **GC module depth** — ball-in-court, super/PM personas, fieldsets, researched Tier-1/2/3 field sets
  across the 73 modules. **Release pipeline hardened** (version from git tag; single-draft publish).

## v0.1.52 — GC dashboard redesigned as a command center
- **Dashboard rebuilt around the new nav rail** — the redundant "All modules" catalog is gone (the
  persistent left rail owns navigation now), and the dashboard is a focused command center: **clickable
  KPI cards** that jump straight to the relevant filtered module (Open RFIs → RFIs · open), a risk
  summary, a prominent **"Ball in your court"** action list (with a caught-up empty state), a grouped
  **Project health** card (budget over/under + safety + lean PPC), trend charts, and Ask AI at the
  bottom — in a two-column layout that stacks on narrow screens.

## v0.1.51 — cost-code workflow: inline add + wider links (roadmap D1 + X1)
- **Inline "add new" from reference dropdowns (D1)** — every reference field (cost code, location, sub…)
  now has a "＋ Add new …" option that creates the record without leaving the form and selects it. So
  while coding a budget line you add the cost code on the spot. Falls back to the target module's
  required field, so a new Cost Code is created with its `code`.
- **Cost-code links on cost-impacting modules (X1)** — RFIs, CORs, change events, PCO requests and
  proposals gained a `cost_code` reference, so impacts tag a code and roll up to the budget (joining
  budget/commitment/direct-cost/timesheet). `/modules` now exposes `title_field`/`ref_prefix`.

## v0.1.50 — GC portal navigation rail + module improvement roadmap
- **Persistent left nav rail in the GC portal** — opening a module used to replace the whole panel, so
  moving between the 73 modules meant going "back" every time. Now a sticky left rail (Dashboard +
  filter + favorites + collapsible sections) stays visible and loads each module into a content pane —
  jump anywhere in one click, with the active module highlighted. (Stacks above the content on phones.)
- **GC module deep-dive roadmap** ([docs/gc-modules-roadmap.md](docs/gc-modules-roadmap.md)) — a
  field-by-field audit of all 73 modules against how large GCs run these workflows, with cross-cutting
  themes (cost-code links everywhere, ball-in-court
  /assignee, fieldsets, inline add-from-dropdown, super-vs-PM views, cross-module conversions) and
  tiered per-module priorities. How to **add cost codes**: Construction → Cost Codes (Resources) → + Add.

## v0.1.49 — left rail revamp (crisp icons + expandable labels)
- **Modernized the left icon rail** — the oldest piece of the UI. The cryptic `⌗`/`≣` Unicode glyphs
  are replaced with crisp inline **SVG icons** (hierarchy / layers / flag / gear), and the rail is now
  **expandable** (VS Code activity-bar style): a `‹`/`›` toggle widens it 46→150 px to show **Tree /
  Layers / Issues / Tools** labels beside each icon, persisted to localStorage. Structure unchanged
  (the four Model-workspace panels were already the right set); this is legibility + feel.

## v0.1.48 — closeout package reachable in the UI
- **Full turnover .zip now has UI access** — the `closeout/package.zip` deliverable (as-built IFC +
  COBie/QTO/space workbooks + status report + closeout records) worked via the API but had **no
  button anywhere**. Added it to **Save ▾ → Closeout package (.zip)** and the **Tools → Exports**
  panel (📦). Found by debugging every menu item against a real demo project. (The `.mmproj` bundle —
  geometry + full database + blobs, round-trips via Open/Save — was already wired.)

## v0.1.47 — end-to-end demo hardening (closeout filename + generate→finance)
Two real bugs found by a full login→closeout demo run (only surface with a realistic project):
- **Closeout package 500** on any project name containing a non-latin-1 char (em-dash, smart quote,
  accent, emoji): the name went into a `Content-Disposition` header, which HTTP encodes as latin-1 →
  crash. Fixed with a shared `safe_filename()` (also hardens the `.mmproj` bundle vs CJK/emoji).
- **Finance showed $0 right after generating a model**: generate didn't persist a cost budget, so
  Sources & Uses read the empty starter. Generate now seeds a `dev_budget` (land + hard from GFA×$/sf
  + soft) → Finance immediately shows the real deal ($21.2M uses on the demo).
Regression-locked: the closeout test now uses an em-dash project name; the generate test asserts
non-zero Sources & Uses. Full gate green (API 30/30).

## v0.1.46 — Studio UX hardening
- **Studio layout bug fixed** — `#panel-studio` carries both `.fullpanel` and `.studio`, and
  `.fullpanel.active{display:block}` was overriding `.studio{display:flex}`, so the node canvas grew
  to its full 1700 px content instead of filling the viewport. Now a higher-specificity rule forces
  the flex column; the canvas is viewport-bounded and **scrolls internally**.
- **Touch support** — node dragging uses pointer events (+ `setPointerCapture`, `touch-action:none`),
  so it works on tablets/phones, not just mouse.
- **Empty-state guidance** — an in-viewport hint ("add a node… then wire… Run", or "connect the API")
  when the canvas is empty.
- **Smarter node placement** — new nodes drop into the current scroll viewport (with a small cascade)
  instead of a fixed corner that overlapped after a few adds.

## v0.1.45 — custom unit-mix editor (A1b — Test Fit A-theme complete)
- **Define your own unit mix** — the Test Fit panel gains an editor to add/remove unit types
  (name · target SF · mix %), saved to localStorage. "Compare schemes" sends it with `with_defaults`
  so your mix is **ranked against the built-in presets**. Completes A1b — the Test Fit A-theme
  (A1–A6 + egress check + auto egress geometry) is now fully done.

## v0.1.44 — P6 .xer → 4D dates + auto code-positioned egress (A2)
- **Primavera P6 schedule → 4D dates** — `POST /projects/{id}/schedule/import-xer` parses a P6 `.xer`
  (TASK table) and stores it; the **4D scrub then reports real calendar dates** (`source:"p6"`, the
  project's start→finish window) instead of relative takt days. New "⬆ Import P6 schedule (.xer)"
  button beside the 4D tool; a 📅 line shows the imported range. `DELETE …/import-xer` reverts to takt.
  (Element build-order stays takt-derived — no per-activity element mapping is claimed.)
- **A2 — auto code-positioned egress geometry** — generated models with a service core now place
  **two means of egress**: the core stair plus a second "Egress stair 2" at the opposite corner
  (≥⅓-diagonal remoteness, IBC 1007.1.1). Completes the generative half of Test Fit A2 (the egress
  pass/fail check already existed).

## v0.1.43 — demo-aware empty states, mobile/PWA polish, P6 .xer import
- **Demo-aware empty states** — the GC portal & drawings no longer show a misleading "pick a project"
  in the viewer-only Pages demo (there's no backend there). A shared `noProjectHtml` explains it's the
  viewer demo + links to the full app; in the real app it gives an actionable "create/open a project"
  hint.
- **Mobile / PWA polish** — `touch-action:none` + `overscroll-behavior:none` on the 3D container so
  camera-controls own touch gestures (orbit/pan/pinch) instead of the page scrolling; PWA install meta
  (theme-color, apple-mobile-web-app-*, viewport-fit=cover); bigger tap targets for the rail + viewer
  tools on phones.
- **Primavera P6 .xer schedule import** — `schedule.parse_xer` reads the TASK table (planned→actual→
  early date fallback) into the activity rows the CSV mapping path consumes, so a P6 schedule can drive
  the 4D scrub. `.mpp` stays export-to-XML/CSV (proprietary binary). Gated in test_analysis.
- **Roadmap reconciled** — A-theme status clarified (A1/A3/A4/A5/A6 + egress check + parking geometry
  + polygon offset done; only unit-type presets + auto-placed egress geometry remain); schedule-import
  + "what else to import" + Revit/Navisworks-plugin + IFC5-alpha verdicts recorded.

## v0.1.42 — main.ts refactor round 2 (account/admin UI) + login on modalShell
- **Modularization** — the account / auth / admin surface (sign-in + SSO, reset, account menu,
  self-service password, admin user management, audit log, project-member management; ~330 lines)
  moves out of `main.ts` into `account/accountUI.ts` behind a small deps object. With round 1's
  connections extraction, **`main.ts` drops from 1205 → 657 lines**.
- **Login fix** — the sign-in dialog hand-rolled its own overlay and so lacked Esc-to-close, a focus
  trap and dialog ARIA. It's now built on the shared `modalShell` like every other modal — consistent
  look + behaviour + accessibility.

## v0.1.41 — main.ts modularization (round 1) + XSS hardening
- **Security (stored-XSS fixes)** — admin modals interpolated user/remote values straight into
  `innerHTML`. Now escaped via a shared `escapeHtml`: connection **name/type**, Procore **project ID**
  + sync info, **browsed DB** column names & cell values, and audit-log fields (the audit modal's
  weaker local escaper is replaced). No user- or database-controlled string renders as HTML anymore.
- **Modularization + perf** — the ~240-line admin **Data-connections UI** (list/add, Procore
  schedules + field-mapping, SQL browser) moved out of `main.ts` into `connections/connectionsUI.ts`,
  **lazily imported** so its ~13 kB leaves the initial bundle and loads only when an admin opens it.
  `main.ts` drops from ~1205 to 963 lines. Behavior unchanged; verified via the vite transform
  pipeline + typecheck + web unit tests.

## v0.1.40 — viewer camera fix + egress surfaced (UX verification pass)
- **Fix: NaN camera / broken 3D view** — loading a model while the Model workspace wasn't visible
  (e.g. a reload that restored the Finance/Drawings workspace, or opening a model from another
  workspace) created the viewer in a 0×0 container, making `camera.aspect` = 0/0 = NaN; the subsequent
  `fitToSphere` baked NaN into the camera position and the viewport showed nothing once you switched
  to Model. Now the fit is **deferred while the viewport is hidden** and run once it has real
  dimensions, the aspect is forced valid synchronously (OBC's ResizeObserver is async), and a
  hard camera reset recovers an already-NaN camera that `setLookAt` alone can't clear.
- **Egress / life-safety now reachable** — the deepened A2 check (occupant load, travel distance,
  required exits, exit separation) was computed but had no UI. `test-fit/compare` now returns the
  plate-level egress result and the Test Fit panel shows a ✅/⚠️ life-safety line with the figures and
  any code flags.
- Found during a full hands-on verification of everything built this session (viewer tools, Studio
  node editor, generate+parking, families/import, deck, lien waivers, COBie, dashboard, 4D) — all
  others confirmed working end-to-end.

## v0.1.39 — accessibility pass (tab semantics, labels, live region)
- **a11y** — the workspace switcher and finance sub-tabs now carry `role="tablist"`/`role="tab"` with
  `aria-selected` kept in sync as you switch (screen readers announce the active view); the role/persona
  picker gained an `aria-label`; and the status bar is a polite `role="status"` live region so status
  updates are announced. Builds on the existing landmarks (`main`/`nav`/`header`/`footer`), `lang`, and
  icon-button `aria-label`s.

## v0.1.38 — Redis rate limiting (multi-worker) + dashboard perf
- **Distributed rate limiter** — set `AEC_REDIS_URL` and the per-IP request limit is now shared across
  workers/processes via an atomic Redis `INCR`+`EXPIRE` (fixed 60s window), so the limit holds under a
  multi-worker deployment instead of being per-process. Fail-open: any Redis error falls back to the
  in-process bucket so limiter infrastructure can never take the API down; redis is imported lazily
  only when the URL is set (no new dependency for the single-worker/desktop build). New `test_ratelimit`
  gate covers the enforcement path (health/metrics exempt, 429 + Retry-After past the limit).
- **Dashboard perf** — the GC dashboard no longer loads and JSON-parses every record across all
  modules. Status tallies now come from a single indexed `GROUP BY workflow_state` per module (zero
  JSON), and the `data` blob is parsed only for the **active** (non-terminal) records that feed
  overdue + action-items — so completed-record-heavy projects build the dashboard far faster. Output
  is byte-for-byte identical (`test_dashboard` unchanged).

## v0.1.37 — COBie field depth (C2) + investment-deck market/timeline slides
- **COBie model-derived field enrichment (C2)** — the handover sheets gain the fields FM teams use:
  Space net/gross **area** + usable height (from Qto), Type **manufacturer / model / warranty /
  expected-life / replacement-cost / color / material**, Component **serial / install-date /
  warranty-start / tag / asset-id**, plus a new **Attribute** sheet that flattens every remaining
  property set (Name/Value/SheetName/RowName) so nothing is lost in handover.
- **Investment deck — Market & Timeline slides** — the pitch deck grows from 4 to 6 slides: a
  **Market & positioning** slide plotting the deal's yield/IRR/soft-cost against conceptual benchmark
  bands, and a **Development timeline** gantt bar (predev → construction → lease-up → stabilization →
  exit, durations from the saved scenario), plus a **site photo** on the cover from project attachments.

## v0.1.36 — printable statutory lien-waiver documents
- **Lien-waiver documents / PDFs** — pay-app accounting, lien-waiver *record tracking* and COBie
  enrichment already shipped earlier; this adds the piece they lacked: the actual **printable
  statutory waiver form**. `cost.lien_waiver` renders the four conditional/unconditional ×
  progress/final forms (Cal. Civ. Code §8132–8138 style) from a pay application — notice, body and
  amount (current payment due for progress, contract sum to date for final) — exposed as
  `GET /projects/{id}/cost/lien-waiver` (JSON) and `.pdf`, plus a "⚖ Lien waiver / release" action in
  the viewer cost panel. Complements the existing `POST /cost/lien-waiver` record-tracking endpoint.

## v0.1.35 — Test Fit depth (egress · parking · polygon footprint · proforma)
- **Deeper egress / life-safety check (A2)** — `test_fit.egress` now screens the big four IBC fails:
  max travel distance, **occupant load** & required **egress width**, minimum **number of exits**, and
  **exit separation** (½ diagonal / ⅓ sprinklered) — with per-check detail + flags (e.g. an assembly
  hall trips ≥4 exits). Back-compatible with the prior keys.
- **Parking as real IFC geometry** — `generate(..., parking=N)` lays out a surface lot of `N`
  IfcSpace `PARKING` stalls (2.5×5 m + drive aisles) on a dedicated *Site Parking* storey, each with
  area QTOs. Exposed on the generate API + a "Surface parking stalls" field in the proforma form.
- **True polygon-offset footprint** — for `lot_polygon` parcels the buildable footprint is now a real
  inward setback (`offset_polygon`, handles reflex vertices + over-collapse), surfaced as
  `buildable_polygon`, instead of a bounding-box approximation.
- **Optimize tied to the proforma** — the generative sweep's yield-on-cost + new **development
  spread** (bps vs exit cap) come from the canonical `proforma.returns` functions (with stabilized
  occupancy), so the quick screen matches the full underwriting; you can rank by `dev_spread_bps`.

## v0.1.34 — import external IFC families (M3) + visual node editor (M4 complete)
- **Import IFC type content** — bring manufacturer / 3rd-party families into a project from any IFC:
  `families.import_types_from_ifc` copies every IfcTypeProduct (with geometry) in via
  `project.append_asset` (deduped, idempotent), then they're placeable like the built-in catalog.
  New endpoint `POST /projects/{id}/families/import` + *"⇪ Import IFC families…"* in the authoring
  panel. Completes M3.
- **Studio — visual computational graph (M4)** — a new **Studio** workspace renders the Dynamo/
  Hypar-style compute engine as a node editor: drag node types from a palette, wire output→input
  ports (click-to-connect, SVG bezier edges), edit params inline, and **Run** to execute the graph
  server-side in dependency order with values flowing through the wires (zoning → cost → yield, etc.).
  Graph persists locally; shown for developer/architect/engineer personas. Completes M4 — the whole
  **M-theme (M1–M4) is now done**.

## v0.1.33 — material layer sets + family library (M3)
- **Layered construction assemblies** — generated models now carry real **IfcMaterialLayerSet**
  data on walls, slabs and roofs (e.g. exterior wall = brick · cavity · insulation · CMU · gypsum),
  the way Revit's compound structures work — attached via IfcMaterialLayerSetUsage and chosen from
  `IsExternal` / slab type. Feeds take-off, U-value and schedules.
- **Expanded parametric family library** — the placeable catalog grows from 16 to 37 entries across
  new **Lighting**, **MEP** (AHU, fan-coil, diffuser, electrical panel), **Structural** (steel
  column/beam) and **Transport** categories, plus more furniture/sanitary/appliances. Families are
  now **parametric**: pass `dims` to place a distinctly-named, correctly-sized **type variant**
  (Revit-style type families). New element classes get palette colours too.

## v0.1.32 — first-person walkthrough (M2 complete)
- **Walkthrough mode** (🚶 toolbar) — Matterport-style first-person navigation: drops to eye height
  (1.6 m), **W/A/S/D** to walk (locked horizontal so you stay on the floor) and drag to look around.
  Switches to a perspective view on enter and restores your prior camera on exit. Completes M2.

## v0.1.31 — sun & shadow study (M2)
- **Sun / shadow study** (☀ toolbar) — drive the render-mode sun by **date, time-of-day and
  latitude/longitude** with a live panel; shadows track the real solar arc (NOAA solar-position
  math), with warm low-angle light and a below-horizon night state. Opening it auto-enables render
  mode. Pure solar math is unit-tested.

## v0.1.30 — PBR materials + free Revit import
- **PBR pass (M2)** — render mode now upgrades plain lit surfaces to `MeshStandardMaterial`
  (roughness/metalness, keeps the M1 IFC colours) lit by an **IBL studio environment** for soft
  ambient + reflections, on top of the sun/shadows. Reversible; Fragments' own shader meshes are
  left untouched so the engine renderer is never at risk.
- **Free Revit → IFC path** — the Open menu now has *"Free: export IFC from Revit (no bridge)…"*:
  a guide to Revit's built-in IFC export + the free, open-source **pyRevit**, so getting a model in
  doesn't require the paid Autodesk bridge.
- **Docs** — library interoperability evaluation (roadmap §L: IFClite, pyRevit, FreeCAD, Pascal
  Editor) and ADR 0001 on dependency bundling & the signed-update policy (deps are pinned and ship
  inside the app update — never background-updated independently).

## v0.1.29 — render mode (M2 start)
- **Viewer render mode** (◓ toolbar) — a directional **sun with soft (PCF) shadows**, hemisphere
  sky/ground fill + fill light, **ACES tone mapping** and sRGB output, and a shadow-catching ground
  plane. Off by default (flat shading stays the cheap default); re-applies as new models load.
  First step toward Revit/Rhino/Matterport-style rendering.

## v0.1.28 — faster large-model loading
- **Download progress** — large models stream with a live "downloading N% (x/y MB) → preparing
  geometry" label instead of a generic spinner that looked frozen.
- **ETag revalidation** — `model.frag` now serves an ETag + `must-revalidate`: unchanged models
  re-open instantly via **304**, while a republished/edited model is always refetched (fixes a
  stale-cache bug where an immutable 1-year cache served the old geometry forever).

## v0.1.27 — computational graph (M4 start)
- **Dynamo-style node graph** over the pure engines: `GET /compute/nodes` (palette) and
  `POST /compute/graph` run a {nodes, edges} graph in dependency order (zoning → structure / takt /
  cost → yield-on-cost). Zero-touch: function params become input ports, dict returns become outputs.

## v0.1.26 — IFC materials & surface colours (M1 start)
- **Materials & surface styles** — generated/dome models get an IfcMaterial + IfcSurfaceStyle colour
  per element class (concrete, glazing, steel, vegetation…), so models carry real material data.

## v0.1.25 — gamified getting-started
- **Getting-started checklist** — a floating progress pill guides new users through the 6 core
  actions (load a model, generate, test-fit, budget, project, memo) with a progress bar + celebration.

## v0.1.22 — 4D & the vertical assembly line
- **4D construction sequencing** — map model elements onto a takt plan; **scrub the build sequence
  in the viewer** (a slider isolates what's built to date).
- **Takt / line-of-balance chart** (SVG) and an **egress check** (two means + travel distance).

## v0.1.21 — lean & multi-period billing
- **Lean / Last-Planner PPC** — a weekly-plan module + Plan-Percent-Complete analytics with reasons
  for non-completion.
- **Multi-period pay apps** — roll completed-to-date across successive draws; retainage release on
  the final application.

## v0.1.20 — underwriting realism (II)
- **Capital reserves above NOI**, **citable guardrail bands** (sourced from the benchmarks), and
  **Test Fit optimize seeded from the live project** (real land + cost budget).

## v0.1.19 — built-world techniques (Willis · Salvadori · CM/RE research)
- **Takt / line-of-balance** scheduling with a just-in-time delivery plan (R2).
- **Lean PPC** engine (R4) and citable **benchmarks + a comparables module** (R5).

## v0.1.18 — structural-system advisor (R3)
- Pick a plausible system by height/span (flat-plate · shear-core · outrigger) with rough member
  sizing + a load-path read — driving the generated frame (after Salvadori).

## v0.1.17 — form follows finance (R1)
- Generative massing / Test Fit reward **daylight-limited rentable depth** + core efficiency — the
  highest rentable yield wins, not max FAR (after Carol Willis).

## v0.1.16 — underwriting realism (I) + Finance revamp
- **Risk-adjusted** specialty/operating revenue + **guardrails** that flag returns outside market
  bands. Finance reorganized into sub-tabs with a sticky live-returns bar.

## v0.1.15 — pitch deck
- One-click **pitch-deck PDF** variant of the investment memo (B6).

## v0.1.14 — generative optimize + real parcels
- **Generative design** sweeps unit-mix × parking and ranks by yield-on-cost (A5); **real lot
  polygons** drive the program by shoelace area (A6).

## v0.1.13 — Test Fit + property/tax
- **Test Fit** — corridor unit-mix layout, parking solver, scheme compare (A1/A3/A4); **property &
  tax assumptions** feeding OPEX (B3).

## v0.1.11 — specialty assets
- On-site **energy** (solar/wind/battery/rainwater) and **vertical-farm (PFAL)** revenue flow into
  capex / revenue / opex (B4).

## v0.1.10 — developer cost portal
- Line-item **hard/soft cost budgets** (B1), **Sources & Uses** (B2), and a one-click **investment
  memo PDF** (B5).

## v0.1.6–0.1.8 — accounts, AI & hardening
- **SSO** (Google / Microsoft / Procore) + a no-admin free-tier model; first-run **onboarding + tour**.
- **"Ask AI"** project assistant over a live snapshot; AI risk summaries + drafted RFIs.
- **Field capture** (offline photo → punchlist/observation, syncs on reconnect).
- Production hardening — rate limiting, security headers, auth-secret fail-safe, takeoff caching.
- Full generative lifecycle from zoning (frame + units + envelope + core).

## v0.1.0–0.1.5 — foundation
- **BIM viewer** (Three.js + Fragments, offline WASM), federation, clash, IDS, 2D drawings/sheets,
  in-viewer authoring round-trip.
- **GC portal** — config-driven modules (RFIs, submittals, change-order chain, daily, QA, safety…),
  CPM, pay apps, dashboards.
- **Development proforma** — S&U with interest-reserve circularity, XIRR/NPV/EM, JV waterfall,
  sensitivity + Monte Carlo.
- **Generative massing + family library**; free single-project **desktop app** with signed,
  auto-updating releases.
