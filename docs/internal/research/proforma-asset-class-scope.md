# Proforma scope — what six institutional CRE models require that ours cannot express

**Date:** 2026-08-01 · **Method:** structural read of six externally-authored underwriting workbooks
(office development, apartment acquisition w/ Monte Carlo, value-add apartment, multifamily
renovation, hotel, data-center development), compared against `aec_api/proforma/` and the `lease`
module. Sheet inventories and concept vocabulary were extracted from the workbook XML; **no formulas
were copied and none of their content is reproduced here.** The models are third-party copyrighted
works used as a *requirements survey*, not as a source. Everything proposed below is standard
industry math to be implemented independently.

## The headline finding: most of what's missing is REACH, not capability

The instinct is "we need a rent roll". **We already have one.** The `lease` module carries
`base_rent_annual`, `escalation_pct`, `free_rent_months`, `recovery_psf`, `ti_allowance_psf`,
`start_date`/`end_date`, `suite`, `rentable_sf`, `renewal_options`. Five engines consume it:
`rentroll.py`, `net_effective.py`, `leasemgmt.py`, `rent_scrub.py`, `cam.py`.

**The proforma cannot reach any of it.** `Ops` takes a single blended `potential_rent_annual`, and
`operating_noi()` multiplies it by a *linear* lease-up ramp. Grep for `lease` inside `proforma/`
returns only the lease-*up curve* — the rent roll and the proforma never meet.

`rentroll.py`'s own docstring states the intent:

> *"…so a built asset's **actual** operations feed back into the **proforma** + appraisal (income
> approach)."*

That sentence describes a wire that does not exist. Same shape as R22-PRODUCTION, where
`production_quantity` carried the model's join key and only cost consumers read it.

## Concept map — surveyed models vs. us

| concept | in the surveyed models | ours |
|---|---|---|
| Waterfall, pref, promote, IRR hurdles | all six | ✅ `waterfall.py` |
| Equity multiple, IRR, exit cap, reversion | all six | ✅ `returns.py`, `residual.py` |
| S-curve draws, construction period | office, data centre, renovation | ✅ `draws.py` |
| Monte Carlo | apartment MC | ✅ `monte_carlo.py` |
| Sensitivity | several | ✅ `sensitivity.py` |
| CAM / expense recovery | office, value-add | ✅ `cam.py` — but **not** in the proforma |
| Net effective rent, free rent | office, value-add, apartment | ✅ `net_effective.py` — **not** in the proforma |
| Rent roll / in-place income | apartment, value-add | ✅ `rentroll.py` — **not** in the proforma |
| **Rollover: downtime, renewal probability, releasing cost** | office, value-add, apartment | ❌ nothing |
| **TI/LC as a proforma capital cost** | office, value-add | ❌ field exists on the lease; no cost line |
| **Unit mix + per-unit renovation schedule** | value-add, renovation | ❌ nothing |
| **Hotel: ADR / occupancy / RevPAR, departmental P&L, penetration index** | hotel | ❌ nothing |
| **Capacity-based revenue (kW / MW)** | data centre | ❌ nothing |
| **Mezzanine / second-position debt** | office, data centre | ❌ one loan only |
| **Refinance mid-hold** | data centre, value-add | ❌ nothing |

## Why the single blended income line is the binding constraint

`Ops.potential_rent_annual` is one number for the whole asset. That is expressible for a simple
stabilised deal and **cannot represent any of the six**:

* an **office** deal needs per-suite expiry, downtime, and TI/LC spent *at* re-lease;
* a **value-add apartment** deal needs unit types renovated on a turn schedule, each with a rent
  premium that begins when that unit turns;
* a **hotel** has no "rent" at all — revenue is ADR x occupancy x rooms, plus departmental revenue
  with its own margins;
* a **data centre** sells capacity, not floor area, and leases in MW blocks with absorption;
* **any** commercial deal with recoveries needs gross rent, recovery income and the opex it recovers
  against modelled separately — netting them into one figure destroys the reimbursement.

## Proposed scope, in dependency order

**1. Income basis (foundation).** Let a deal state its income as either the blended figure it uses
today, or a **basis derived from detail**. Same pattern as `option_economics.BASIS_*`: the derived
value and the declared value both retained, so `declared_disagrees_with_derived` can exist. Nothing
is inferred silently — a deal that supplies neither is refused, not defaulted to zero.

**2. Rent-roll basis** — wire `rentroll.summarize` + `net_effective.roll_up` + `cam.reconciliation`
into (1). This is pure reach: three engines, all tested, none reachable from a proforma today.

**3. Rollover engine** — expiry → downtime → releasing cost → renewal-vs-new mix. Prerequisite for
office and any multi-tenant asset. TI/LC becomes a proforma cost line here, not a lease field.

**4. Unit-mix / renovation schedule** — per-unit-type renovation cost and premium on a turn curve.

**5. Asset-class operating models** — hotel (ADR/occ/RevPAR + departmental) and capacity (kW/MW), each
as an income basis under (1) rather than a fork of the proforma.

**6. Capital stack depth** — mezzanine and refinance.

**Sequencing rationale:** (1) and (2) unlock the assets we already hold data for and are mostly
wiring. (5) is the largest genuinely-new build and should not start before (1), or each asset class
grows its own parallel proforma — the two-parallel-stores problem that `R32-FILE-GENERATED` already
had to unwind once.

## Refusals this scope must carry

Every item below is a place where a plausible number is worse than no number:

* **a hotel is not a lease.** If a hotel deal reaches the rent-roll basis, refuse — do not treat ADR
  as rent;
* **recoveries must not be netted into base rent.** Once netted, the reimbursement is unrecoverable
  and the opex ratio is wrong in a way that still looks sane;
* **a renovation premium must not begin before the unit turns.** Applying it from day one is the
  single most common way a value-add deal is overstated;
* **downtime is not optional.** A rollover model with no downtime produces continuous occupancy,
  which is strictly better than reality and reads as a modelling result rather than an omission;
* **declared vs derived income must both survive.** If a rent roll implies £X and the deal declares
  £Y, that disagreement is the finding — resolving it silently destroys it.
