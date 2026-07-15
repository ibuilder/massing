# Marketing copy — ready to paste

Reusable messaging for the site, README, social, and launch posts. Everything here reflects
shipped capabilities (no vaporware). Tone: confident, concrete, builder-to-builder.

## Taglines
- **The whole building lifecycle, on one model.**
- From a zoning lot to a finished building — generate it, underwrite it, build it, hand it over.
- From a lot to a closed sale — one IFC model carries the deal all the way to disposition.
- The AEC market is a patchwork of point tools. This isn't.
- IFC-native, open, self-hosted. No per-seat license.

## One-liner
An open, self-hosted AEC platform that spans **acquisition → turnover on one IFC model** — BIM
viewer, generative design + Test Fit, development proforma, GC portal, 4D construction and turnover,
disposition & appraisal.

## Elevator pitch (≈60 words)
Most teams stitch together a feasibility tool, a BIM authoring tool, a construction-management
platform, and a handover tool — none of them talking. This is one IFC-keyed platform for the whole
lifecycle: generate a building from a zoning envelope, underwrite the deal, coordinate the model,
run the job, and hand it over — open, self-hosted, and free to run on one machine.

## Feature one-liners
- **Site feasibility in seconds** — site area + FAR/height/coverage/setbacks → max buildable GFA (binding constraint: FAR vs. envelope), unit yield, parking demand, open space — then reconciled against your model's actual GFA (FAR used, headroom, over/under). The "should we build it?" answer before you draw a line.
- **Generate from zoning** — lot + FAR + setbacks → a real IFC building (frame, units, envelope, core) + a solved proforma.
- **Test Fit** — corridor unit-mix, parking solver, scheme compare, generative yield-on-cost optimize.
- **Developer finance** — line-item budgets, Sources & Uses, specialty (energy + vertical farm), investment memo + pitch deck.
- **Underwriting that's honest** — risk-adjusted revenue + guardrails that flag returns outside market bands.
- **GC portal** — RFIs, change orders, pay apps, CPM + takt + 4D, lean PPC, safety, closeout — config-driven.
- **Model → discipline sheet set → AIA issuance** — generate a full 2D drawing set from the model: one NCS-numbered series per discipline (S-/A-/M-/E-/P-/FP-/**FA- Fire Alarm**/T-…), a plan per level, plus sections/details/schedules — hundreds of sheets in a fraction of a second. Then release it the way an A/E office does: dated **issuances** for a purpose (SD → DD → CD → Permit → Bid → Construction → Record), each snapshotting exactly which sheets at which revision went out, with the front-of-set **sheet × issuance matrix** and a per-issuance transmittal.
- **Spec book → submittal register** — paste your specifications, get a typed submittal log (shop drawings, product data, samples…) with missing-submittal coverage. AI when you have a key, a built-in parser when you don't.
- **Off-plan listing kit** — a BIM-native Listing Fact Sheet + a signed public link/QR, auto-filled from the model & proforma.
- **Tri-approach appraisal** — cost + income + sales-comparison reconciled into a Valuation report, RESO-aligned for MLS.
- **Earned Value Management** — one ANSI/EIA-748 metric set (CPI/SPI, the EAC/ETC/VAC/TCPI forecast family, Earned Schedule) with a twist: earn value off the *physically installed model*, not just a billing SOV — so front-loaded progress gets caught. S-curve, CPI–SPI quadrant, and a captured-snapshot performance trend.
- **Resource-loaded scheduling** — tie crews / equipment / material (with rates) to schedule activities and cost codes; get a cost-loaded manpower histogram, unit + cost S-curves, over-allocation against an availability cap, and a leveling advisory that smooths peaks within CPM float.
- **WIP schedule + contractor statements** — the construction-accounting artifact: percentage-of-completion (cost-to-cost) → earned revenue vs billed → over-billing (a liability) or under-billing (a cash-draining asset), plus retainage, gross profit and backlog — with a portfolio roll-up sorted by cash risk. Rolls straight into a **POC income statement** and a **contract-position balance sheet** (contract asset/liability, retainage, AP, net contract working capital). The accounting twin to earned value.
- **General ledger + cost traceability by GlobalId** — a balanced double-entry journal (job cost, owner billing, WIP percentage-of-completion adjustment) with a construction chart of accounts and a trial balance; then tag any cost record to the **IFC elements it pays for** and see coverage per cost code and "what did *this* column cost?" by GlobalId — the model → resource → cost → GL link a cost-code-only ledger can't make.
- **Author the model, tag the standards** — draft structural/MEP/architectural families server-side (GUID-stable IFC), then set typed properties and attach Uniclass / OmniClass / Uniformat classifications right from the element panel.
- **Draw like you mean it** — in-browser walls/columns/slabs with SketchUp-style inference (auto on-axis / parallel / perpendicular snapping), sloped-top walls (parapet / shed / gable), procedural mesh, and full **undo / redo** — every edit versioned and GUID-stable. For the geometry the recipes can't express, an AST-sandboxed code escape hatch (off by default).
- **Site logistics, furnished & landscaped** — drop cranes, hoists, fencing, sanitary units, laydown, furniture, and planting from a content library; each one auto-classified into the right IFC class + Uniclass/OmniClass, with temporary logistics time-phased on the 4D slider.
- **The RFI you didn't have to write** — a decision-readiness audit surfaces the information gaps a builder would otherwise ask about — failed code checks, missing details, model-data holes, open clashes — as one ranked resolve-before-you-issue list.
- **Labour from the model** — productivity rates (man-hours per unit) turn the model's real quantities into labour cost, crew-days, and a duration estimate.
- **Code checks that know the edition** — occupant loads and citations follow the IBC edition your jurisdiction actually adopted, not a generic default.
- **Grounded in the literature** — Willis (form follows finance), Salvadori (structure), the Empire State takt assembly line.

## One-pager — Earned Value Management
**The problem.** A pay-app SOV can be front-loaded: reported progress runs ahead of what's actually
built. Dollar SPI also breaks down near the finish (it drifts back to 1.0 even on a late job).

**What this does.** One ANSI/EIA-748-aligned metric set, computed by joining schedule earned value with
cost actuals **by cost code (the control account)**:
- **Indices + variances** — CPI, SPI, CV, SV, % complete / % spent, each with a health band.
- **Forecast family** — the four canonical EACs, ETC, VAC, and TCPI-to-budget/EAC, shown together with
  a stage-adaptive recommendation (the "best" EAC depends on how far along you are).
- **Earned Schedule** — time-based ES / SV(t) / SPI(t) / IEAC(t) → a forecast finish that stays honest
  at completion.
- **EV measurement methods** — percent, 0/100, 50/50, units-complete, milestone, LOE (rules of credit).
- **Model-based EV** — earn value off *field-verified installed model elements*; when schedule EV runs
  materially ahead of physical installation, it flags a likely front-loaded SOV.
- **Visuals** — the PV/EV/AC S-curve, a **CPI–SPI quadrant** (project + every control account), and a
  **captured-snapshot CPI/SPI trend** so you can see whether efficiency is improving or slipping.

Every number exports to a signed PDF report. Runs fully offline; no per-seat license.

## Sample social post (X / LinkedIn)
> Shipped: an open, IFC-native AEC platform that covers the *whole* building lifecycle on one model.
> Type a zoning envelope → it generates a real IFC building and underwrites the deal. Then run the
> job — RFIs, pay apps, 4D — and hand it over with COBie. Free desktop app, no per-seat license. 🏗️
> ↳ massing.build

## Show HN blurb
> **Show HN: Open AEC platform — generate a building from zoning, underwrite it, then build it (one IFC model)**
> The AEC stack is fragmented: separate tools for feasibility, BIM, construction, and handover —
> none share a model. I built one IFC-keyed platform that
> spans acquisition → turnover: generative massing + Test Fit, a development proforma with
> underwriting guardrails, a config-driven GC portal (RFIs → pay apps → 4D), and COBie turnover.
> Open, self-hosted, free single-project desktop app. Grounded in Carol Willis & Salvadori.

## Proof points (for credibility)
- Full lifecycle verified end-to-end (concrete tower + a vertical-farm conversion scenario).
- Signed, auto-updating desktop apps for Windows / macOS / Linux.
- Open stack (IfcOpenShell, That Open / Fragments); IFC is the source of truth.
