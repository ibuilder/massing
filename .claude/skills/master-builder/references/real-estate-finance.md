# Real Estate & Development Finance

The money machinery a master builder keeps as the spine of every decision. Read this for pro formas,
underwriting, return metrics, the capital stack, construction-loan mechanics, and JV waterfalls.

## Contents
1. The three documents
2. Residual land value
3. Return metrics (and what each hides)
4. The capital stack
5. Construction-loan mechanics (incl. the interest-reserve circularity)
6. JV waterfalls & the promote
7. Sensitivity, scenario, and the exit
8. Common traps
9. Tooling & the tokenization frontier

Physics and money are the universal parts of building. The pro forma logic below travels to every
country; only the tax treatment, currency, and market conventions change.

---

## 1. The three documents

Development underwriting reduces to three linked artifacts. Get these right and the deal is legible.

**A. Sources & Uses.** Where the money comes from (senior debt + mezz + equity) and where it goes
(land + hard + soft + financing + contingency). Must balance. The **development budget** is the "uses" side:
- *Land / acquisition* — purchase + closing + carry.
- *Hard costs* — site, structure, envelope, MEP, finishes, contingency (typically 3–10% of hard).
- *Soft costs* — design, engineering, permits & fees, legal, insurance, developer fee, marketing.
- *Financing costs* — loan fees/points, **interest carry / interest reserve** (see §5).

**B. Operating pro forma (stabilized).** The income the asset throws off once leased:
Gross potential rent − vacancy & credit loss + other income = **Effective Gross Income (EGI)**;
EGI − operating expenses = **Net Operating Income (NOI)**. NOI is the number the value hangs on.

**C. Cash-flow model (the returns).** Period-by-period cash flows across the hold — development draw,
lease-up, stabilized operations, and exit — from which IRR, equity multiple, and cash-on-cash are computed.

---

## 2. Residual land value

The developer's core valuation move, and the discipline behind not overpaying for dirt:

> **Residual land value = Gross development value (GDV / stabilized value) − (total development cost
> excluding land) − required developer profit.**

It answers "what can I pay for this site and still hit my return?" It's the bid ceiling in site-led
deals and the sanity check in program-led ones. GDV is usually stabilized NOI ÷ exit cap rate (or
sum of unit sale prices for for-sale product).

---

## 3. Return metrics (and what each hides)

No single metric is sufficient; a builder reads them as a set.

- **Yield-on-cost (development yield)** = stabilized NOI ÷ total development cost. Compare to the
  market **cap rate**; the spread (**development spread**, often ~150–250 bps target) is the
  compensation for taking development risk. If yield-on-cost ≤ exit cap, you're building for free — stop.
- **Cap rate** = NOI ÷ value. The market's required unlevered yield; *lower cap = higher value*.
  Set by asset quality, location, and interest rates. **Exit cap** assumption drives GDV — be conservative;
  small cap moves swing value hugely (value ≈ NOI/cap).
- **Cash-on-cash** = annual pre-tax cash flow ÷ equity invested. Ignores appreciation and time.
- **IRR** = the discount rate that zeroes NPV of all cash flows. Captures timing and magnitude but is
  *manipulable by timing* (early distributions flatter it) and assumes reinvestment at IRR. Use **XIRR**
  for irregular real-world dates.
- **Equity multiple (MOIC)** = total distributions ÷ equity invested. Ignores time but exposes IRRs
  that look great only because they're fast. Always read IRR **and** multiple together.
- **DSCR** = NOI ÷ debt service; **LTV** = loan ÷ value; **LTC** = loan ÷ cost. The lender's tests.
- **Break-even occupancy** = (opex + debt service) ÷ GPR. How much lease-up cushion exists.

---

## 4. The capital stack

Bottom (safest, paid first) to top (riskiest, paid last, highest return):

1. **Senior debt** — construction/perm loan, ~50–70% LTC, first lien, lowest cost, DSCR/LTV covenants.
2. **Mezzanine debt / B-note** — fills the gap above senior, secured by equity pledge, higher rate.
3. **Preferred equity** — a fixed preferred return ahead of common; may be hard or soft pref.
4. **Common equity** — GP/sponsor + LP investors; last paid, unlimited upside, carries the residual risk.

More leverage amplifies returns *and* risk; the master builder sizes debt to survive the downside
(stress DSCR and refinancing), not to flatter the base case.

---

## 5. Construction-loan mechanics — the interest-reserve circularity

Construction loans fund by **draw** against work-in-place, verified by a lender's inspector, on a
schedule of values (see pay apps in the delivery ref). Two subtleties trip most models:

- **Interest reserve.** Interest during construction is usually funded *by the loan itself* into a
  reserve. This creates a **circularity**: interest owed depends on the drawn balance, which includes
  the interest reserve, which depends on interest owed. Solve iteratively (or with a circular-reference/
  goal-seek routine) — a naive spreadsheet either under-reserves or blows up. This is exactly the kind
  of solver Matt's development-finance tooling automates.
- **Draw timing vs. the S-curve.** Draws follow the construction S-curve (slow–fast–slow), not a
  straight line; carry is a function of *when* dollars are outstanding, so schedule compression genuinely
  saves interest.

---

## 6. JV waterfalls & the promote

How profits split between the sponsor (GP) and investors (LP) once the money comes back. The
**waterfall** distributes cash through sequential tiers ("hurdles"):

1. **Return of capital** — LP (and GP pro rata) get their invested equity back.
2. **Preferred return** — LP earns a preferred rate (e.g., 8%) on invested capital before any promote.
3. **Promote / carried interest tiers** — above each IRR hurdle, the GP earns a disproportionate
   share (the **promote**), e.g., 80/20 to a 12% IRR, then 70/30, then 60/40 (a "**promote crescendo**").
   A **catch-up** may let the GP catch to its target share after the pref.

Solving a waterfall means finding, at each period, the split that satisfies each tier's hurdle in
order — a **tiered IRR/hurdle solver**. Model it explicitly; hand-waving the promote is how partners
end up in litigation. State whether hurdles are on **IRR** or **equity multiple**, and whether pref
is **cumulative/compounding**.

---

## 7. Sensitivity, scenario, and the exit

- **Sensitivity** — flex one variable at a time (rent, exit cap, hard cost, lease-up speed, interest
  rate). Report which two or three move the outcome most; those are what to manage.
- **Scenario** — coherent bundles (base / upside / downside) that move several variables together.
- **The exit dominates.** GDV = stabilized NOI ÷ exit cap, and exit cap is an *assumption about a
  future market*. Never let a thin deal survive only on cap-rate compression you can't control.
  Stress the exit; if the deal only works on a lower exit cap than entry, be honest that you're
  betting on the market, not on the building.

---

## 8. Common traps

- **Optimistic exit cap** relative to entry — assuming compression.
- **Contingency too thin** for the project's design maturity and site risk.
- **Ignoring carry** — long entitlement/lease-up periods quietly eat returns via interest and opportunity cost.
- **IRR without the multiple** — fast small wins flatter IRR; check MOIC.
- **Under-reserved interest** — the §5 circularity.
- **Straight-line draws** — misstates carry and DSCR-during-construction.
- **Currency/tax naivety internationally** — model in local currency; note withholding, VAT/GST on
  construction, transfer taxes, and repatriation.

---

## 9. Tooling & the tokenization frontier

For actually building these models and platforms, prefer transparent, auditable engines over black boxes:
- A **development-finance app** with an XIRR solver, the interest-reserve circularity solver, and a
  JV-waterfall tier solver (positioned against Argus/Rabbet-class tools) — this is a tool Matt has
  specified and built; reach for it for underwriting and waterfall work.
- **PropWise** — investment platform with MLS ingestion, a proforma engine, and subscription tiers —
  for pipeline and acquisition analysis.

**Tokenization / fractionalization** is the capital-formation frontier: fractional ownership of an
SPV via tokens. The sober architecture (as in Matt's tokenization platform) is **cap-table-first and
custody-light**: get the SPV, PPM, and cap table right *before* any token layer; flat fee, **zero fund
custody**, and clean broker-dealer and securities analysis. Reason through the structure and the risk
register (SPV/PPM obligations, broker-dealer exposure, token-layer sequencing) — then route the final
securities, KYC/AML, and cross-border questions to qualified counsel. The technology does not change
the securities law; it only changes the plumbing.
