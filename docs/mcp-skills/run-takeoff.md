# Workflow — quantities, cost and carbon for an estimate or a check

Goal: produce quantity/cost/carbon signals for a project from the authored model, so an estimate or a
sanity-check is grounded in real elements rather than a spreadsheet guess.

1. **Confirm a model is loaded.** The quantity engines read the model index. If `carbon_report` returns
   `{"error": "no model loaded for this project"}`, tell the user to publish/convert the model first — the
   takeoff can't run without it.
2. **Carbon + material inventory.** `carbon_report` with `{project_id, gfa_m2?}` → per-element A1–A3
   embodied carbon, Buy Clean limit checks (which materials exceed the procurement limit), and a LEED
   material inventory. Pass `gfa_m2` when you want the intensity (kgCO₂e/m²) normalised.
3. **Schedule exposure.** `schedule_risk` with `{project_id, iterations?}` → P50/P80 completion and the
   delay drivers, so a cost estimate can carry a realistic schedule contingency, not a single date.
4. **Standards / permit gates.** `permit_readiness` and `standards_check` surface the gaps that turn into
   cost (missing sheets, egress deficiencies, unmet requirements) before they're priced.
5. **Report the numbers as given.** Quote the tool's totals and per-category breakdowns. Flag any element
   the report marked as missing a quantity or a material, since those are the estimate's blind spots.

The takeoff is only as complete as the model — always report coverage (how many elements had a usable
quantity vs how many were skipped) alongside the totals.
