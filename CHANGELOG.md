# Changelog

All notable changes to the AEC BIM Platform. Releases are signed, auto-updating desktop builds
(Windows / macOS / Linux); the updater always serves the latest. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/).

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
Six gaps closed from a competitive + open-source scan (OpenConstructionERP, Procore/ACC, RE
asset-mgmt / syndication tools). See [docs/competitive-plan.md](docs/competitive-plan.md).
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
M365) — built to ModelMaker's open, self-hosted, $0 identity (no AR hardware, no MS-365 lock-in).
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

## v0.1.87 — workflow engine upgrades (emanager parity)
Cross-cutting upgrades to the config-driven modules engine — each lights up across all ~75 modules.
Adopted from a gap analysis of the WordPress **emanager** platform + Procore/Autodesk best practice
(see [docs/emanager-gap-analysis.md](docs/emanager-gap-analysis.md)).
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
BIM-native platform can do, because ModelMaker owns the model + proforma. (See
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
  tokens); pick clauses → exhibit PDF, attachable to the record. (Inspired by procore-exhibit-generator.)
- **View & markup** — open any generated contract/CO in the PDF markup overlay to redline
  (fairbuild-style review) before signing.
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
  field-by-field audit of all 73 modules benchmarked against Procore/Fieldwire + how Turner/Suffolk/
  Balfour run these workflows, with cross-cutting themes (cost-code links everywhere, ball-in-court
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
