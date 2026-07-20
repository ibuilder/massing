# Forensic Pro-Forma & Deal Review

How a master builder audits a financial model or development deal someone hands them — their own or
someone else's. Read this whenever the task is to review, critique, sanity-check, stress, or "does this
pencil / is this model right" on a pro forma, underwriting, feasibility study, or investment memo.

The instinct: **trust nothing until it reconciles.** A model is an argument made in numbers; your job
is to find where the argument breaks before an LP's money does. Praise what's genuinely strong, then
be honest about what's wrong — optimism in a pro forma is a defect, not a courtesy.

## Contents
1. Name what the asset actually is (reframe first)
2. The reconciliation pass (does it tie out?)
3. Common model defects — the checklist
4. The three-questions test for any assumption
5. Cost-concentration & the one big move
6. Validate demand before capital
7. How to deliver the critique

---

## 1. Name what the asset actually is (reframe first)

Before touching a number, restate the deal in plain terms stripped of its marketing. A "vertical-farm
skyscraper" that is actually a single-story big-box leased as white-boxes is a **landlord play**, not a
farm — and that reframing changes who the tenants, buyers, and comps really are. The label the sponsor
chose is often the first assumption to audit. Ask: *if I describe this to a skeptical investor in one
sentence with no adjectives, what is it?* Underwrite that.

## 2. The reconciliation pass (does it tie out?)

Before judging the assumptions, check the arithmetic *between* sections. Models drift as they grow;
the same quantity often appears in two places with two values. Verify:

- **Sources = Uses**, and every itemized cost actually flows into Uses (see defect #2).
- **One NOI, used everywhere.** The NOI in the operating tab must equal the NOI feeding DSCR and the
  exit valuation. Two different NOIs = a broken model (defect #1).
- **The narrative matches the model.** The number in the executive summary must be the number in the
  cells. A paper that quotes a $10M NOI while the model computes $3.4M has an integrity problem
  regardless of which is right.
- **Units and orders of magnitude** are consistent — a "$/day" that's really "$/month", a kWh that's
  off by 1000×. Power, in particular, decides energy-intensive deals; distrust the least-legible cell.

## 3. Common model defects — the checklist

Run every model past these. Each one is a real failure seen in real underwriting:

- **NOI gross-up error** — operating expenses *added to* income instead of subtracted (or reimbursements
  double-counted), inflating NOI. NOI = EGI − OpEx. If NOI ≈ rent + opex, it's wrong.
- **Dropped cost lines** — an itemized soft-cost or contingency schedule that doesn't fully flow into
  Sources & Uses. Foot every schedule into the budget.
- **Non-cash items in OpEx** — depreciation or amortization sitting in operating expenses and suppressing
  NOI. NOI is a cash measure; depreciation belongs below it (tax line), not in it.
- **Zero (or trivial) vacancy** — especially for a new, unproven, or single-tenant-class asset. Real
  assets have absorption, rollover downtime, and credit loss. Zero vacancy forever is a tell.
- **Mislabeled rates** — "insurance 5%" that computes at 0.4%; a growth rate applied inconsistently
  across tabs. Check that the printed rate equals the implied rate.
- **Interest-reserve / carry treated casually** — carry funded outside the loan, or the interest-reserve
  circularity ignored (see `real-estate-finance.md` §5). Long entitlement/lease-up periods make carry material.
- **Optimistic exit relative to entry** — an exit cap tighter than entry with no thesis for compression,
  or an exit cap for which no comparable market exists (a brand-new asset class has no established cap).
- **Straight-line construction draws** — misstates carry and construction-period DSCR; real draws follow
  the S-curve.
- **Headcount / opex mismatches** — the staffing narrative (e.g., 25 people) not matching the opex line
  (e.g., 10). Reconcile the words to the cells.

## 4. The three-questions test for any assumption

For each load-bearing assumption (rent, exit cap, cost/sf, absorption, power cost, tenant demand):

1. **What is it, and what does the model do if it's wrong by 20%?** (sensitivity)
2. **What real-world evidence supports it?** Comps, signed leases, quotes — not hope. If the support is
   "a new market with great potential," that's a flag, not a foundation.
3. **Has reality already tested it?** If the assumption rests on named actors or markets, check what
   happened to them. (In one review, every named target tenant — an entire operator class — had gone
   bankrupt in the years after the model was built; that is the demand assumption, answered.)

## 5. Cost-concentration & the one big move

Find where cost concentrates and interrogate it hardest — the top 1–2 line items usually *are* the
project. Compute cost-per-unit-of-benefit and compare alternatives on the same basis (e.g., $/annual-kWh
for a solar line vs. a wind line). A line that is 30% of hard cost for 2% of the benefit is the value-
engineering move that reshapes the whole deal. The biggest lever is rarely spread across the budget;
it's hiding in the largest single number.

## 6. Validate demand before capital

The master-builder correction to "build it and they will come": de-risk the demand *before* the dirt.
Secure anchor/off-take leases or LOIs from a solvent counterparty before closing; phase the build so
the first unit proves the unit economics (and the real operating cost) before the rest is funded from
cash flow instead of a single day-one bet. This is the `build-doctrine.md` staged-validation gate
applied to real estate: prove the edge on a small, real slice before scaling.

## 7. How to deliver the critique

Lead with a one-line verdict (feasible / conditional / no-go) and the honest return, not the sponsor's.
Credit what's genuinely strong first — a critique lands better when it's clearly fair. Then separate
**model-integrity issues** (arithmetic that must be fixed) from **judgment issues** (assumptions that
must be defended), because they're addressed differently. Give ranges and stress cases, not a single
number. End with the smallest set of changes that would make the deal real — the point is to make the
project better, not to win the argument.
