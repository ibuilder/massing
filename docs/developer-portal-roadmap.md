# Developer portal — institutional budgeting, specialty assets & investor materials

Derived from a real institutional development model (M. Emma, *Conversion of Retail Using the
Vertical Farm Method of Indoor Agriculture*, Georgetown 2021) and current CRE practice. The gap:
today the proforma takes flat `cost_lines`; it does **not** model **line-item hard/soft cost
budgets**, a grouped **Sources & Uses**, property/tax assumptions, **specialty revenue/energy**
assets, or **investor-facing materials**. This roadmap builds the developer side out to that depth.

## Grounding (sources)
- Hard vs soft costs, ratios, contingency: [Feldman Equities](https://www.feldmanequities.com/education/hard-costs-vs-soft-costs-in-real-estate-development/),
  [Young Architect](https://academy2.youngarchitect.com/hard-costs-vs-soft-costs/),
  [Willowdale Equity](https://willowdaleequity.com/blog/hard-vs-soft-costs-in-real-estate/),
  [Linneman/Kirsch Ch.10](https://textbook.getrefm.com/chapter-10-development-pro-forma-analysis/).
- Sources & Uses / proforma structure: [LeadDeveloper](https://leaddeveloper.com/real-estate-development-proforma/),
  [Adventures in CRE](https://www.adventuresincre.com/glossary/soft-costs/).
- Offering memorandum / pitch deck: [VIP Graphics](https://vip.graphics/what-to-include-in-a-real-estate-investor-memo/),
  [FocusedCRE](https://focusedcre.com/real-estate-investment-memorandum),
  [RealCapAnalytics](https://www.realcapanalytics.com/blog/a-comprehensive-guide-to-creating-an-effective-real-estate-pitch-deck).

Practice norms to encode: hard ≈ 70–80% / soft ≈ 20–30% of budget; hard contingency 5–10%, soft
("design") contingency ~10%; Uses = Acquisition + Hard + Soft + Financing; Sources = Debt + Equity.

## 1 — Line-item hard / soft cost budgets ★ (the explicit gap)
A structured budget that rolls into the proforma's `cost_lines`. Each line: **category**
(acquisition | hard | soft) · **description** · **$/unit** · **quantity (SF/unit)** · **total =
$/unit × qty** · optional **CSI/cost code**. Per-category **contingency %** on the subtotal.
- Engine `dev_budget.py` (pure): `summarize(lines, contingency)` → per-category subtotals +
  contingency + grand totals; `to_cost_lines()` → the proforma cost tree.
- Storage + endpoints: GET/PUT `/projects/{id}/dev-budget`; `…/dev-budget/cost-lines` (proforma
  seed). Finance UI: a category-grouped editable table with live totals; "Apply to proforma".
- Mirrors the thesis model's **Hard Cost Breakdown** (re-roof, solar, turbines, battery, HVAC,
  chiller, market…) and **Soft Cost Breakdown** (architect, structural/mech/energy/ag consultants,
  expeditor, T&B, design contingency).

## 2 — Sources & Uses
Grouped Uses (Acquisition: purchase, transfer tax, legal/DD, survey/title · Hard · Soft incl.
construction-loan interest) vs Sources (senior debt by LTC/LTV, mezz, LP/GP equity). Endpoint
`…/dev-budget/sources-uses`; balances Uses against sized debt + equity. Per-period draw spread
(reuse the S-curve engine) so financing interest is solved, not hand-keyed.

## 3 — Property & tax assumptions
A project "development assumptions" record: address, block/lot, appraisal, purchase price,
land/building/parking SF, and a **tax table** (school/county/town/fire → total) feeding OPEX.
(Thesis: 2000 Hempstead Tpke — 598,668 land SF, 249,749 building SF, $1.50M taxes.)

## 4 — Specialty assets (differentiator: tie revenue to the model)
Pluggable revenue/energy modules beyond rent, driven off model areas:
- **On-site energy** — solar (SF × $/panel, generation), wind turbines, battery storage,
  rainwater collection → capex + an energy-offset operating credit.
- **Vertical farm / PFAL** — towers × crop cycle × yield × $/lb (wholesale/retail) → revenue;
  lighting kWh load → opex. (Thesis: 23,760 ZipGrow towers, greens + herbs.)
These attach to generated massing (areas → counts) so feasibility flows model → specialty proforma.

## 5 — Investor materials ★ ("generate a presentation with financials")
- **Investment memo (PDF)** — cover · executive summary (location, sponsor, plan, headline IRR/EM/
  yield-on-cost) · property & market · Sources & Uses · hard/soft budget · proforma cash flows &
  returns · JV waterfall · risks & mitigations · timeline/milestones. ~15–25 pp.
- **Pitch deck (10–20 slides)** — the high-level summary version (reuse the memo data).
- Compose from live project data so the deck never drifts from the model.

## Build order
1 (budgets) → 2 (S&U) → 5 (memo PDF) → 3 (assumptions) → 4 (specialty). Each ships independently;
1, 2 and 5 are the headline asks.

## Status
- ✅ **DONE — 1. Line-item hard/soft cost budgets** (dev_budget.py / `/projects/{id}/dev-budget`).
- ✅ **DONE — 5. Investment memo (PDF)** — `report.investment_memo_pdf()` /
  `GET /projects/{id}/investment-memo.pdf`: cover · executive summary · Sources & Uses · cost
  budget · returns (from the latest solved scenario) · risk read. "📄 Investment memo" button in
  Finance. *Next: pitch-deck (slide) variant, market/timeline sections, property photos.*
- ✅ **DONE — 4. Specialty assets (energy + vertical farm)** — `specialty.py` /
  `GET/PUT /projects/{id}/specialty`: on-site solar/wind/battery/rainwater → capex + annual energy
  offset; PFAL towers (from area) → produce revenue + lighting opex + startup capex. Rolls into the
  proforma (capex→hard line, revenue+offset→other income, opex→opex). "⚡ Specialty" Finance panel
  with toggles + Apply. Thesis-grounded defaults. Verified end-to-end. *Next: wind generation curve,
  crop-mix presets, energy storage dispatch.*
- ⏳ 2 Sources & Uses (first-class view) · 3 property/tax assumptions — next.
