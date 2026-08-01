"""PF-INCOME-BASIS — where a deal's operating income actually came from.

`Ops.potential_rent_annual` is **one blended number for the whole asset**, and `operating_noi()`
multiplies it by a linear lease-up ramp. That is expressible for a simple stabilised deal and cannot
represent a multi-tenant one: per-suite expiry, concessions and expense recoveries all collapse into
a single figure that no longer says what it is made of.

Meanwhile the asset's real income is already modelled elsewhere. The `lease` module carries
`base_rent_annual`, `escalation_pct`, `free_rent_months`, `recovery_psf`, `ti_allowance_psf` and the
term dates, and **five** engines consume it — `rentroll`, `net_effective`, `leasemgmt`, `rent_scrub`,
`cam`. `rentroll.summarize()`'s own docstring says it exists *"so a built asset's actual operations
feed back into the proforma"*. Grep for `lease` inside `proforma/` and you get the lease-**up** curve.
**The wire it describes has never existed.** This module is that wire.

## What it refuses to do

**A basis is stated, never guessed.** The failure this prevents is not a missing number — it is a
proforma that answers with someone's typed figure while a contradicting rent roll sits one table
away, and nothing in the output says which was used or that they disagree.

* **`declared` and `derived` are both kept.** If a rent roll implies X and the deal declares Y, that
  disagreement **is the finding**; resolving it silently destroys it. Same argument as
  `option_economics.BASIS_*` and `matched_class` on a takeoff row.
* **Recoveries are never netted into base rent.** Once netted the reimbursement cannot be recovered
  and the opex ratio is wrong in a way that still looks sane. Base rent and recovery income stay
  separate lines, because they behave differently: recoveries track the opex they reimburse.
* **Concessions are reported, not absorbed.** Face rent is what a broker quotes; net effective is what
  underwriting uses. Both are returned, with the load between them, so a deal cannot quietly
  underwrite face rent while calling it income.
* **An empty rent roll is `unavailable`, not zero.** A property with no lease records has *unknown*
  income, not none — and zero is the one value that reads as a real answer.
* **A lease the maths cannot use is NAMED.** `net_effective.roll_up` already counts and names the
  leases it skipped; that list is carried through rather than summarised into a percentage, because a
  count says a problem exists and a name says which lease to open.

This module is pure over the dicts the other engines return — no DB, no model parsing — so it is
deterministic and testable, and it introduces no dependency the proforma did not already have.
"""
from __future__ import annotations

from typing import Any

#: The deal stated a figure and no rent roll was supplied — today's behaviour, still valid.
BASIS_DECLARED = "declared"
#: Derived from the `lease` records via `rentroll` / `net_effective` / recoveries.
BASIS_RENT_ROLL = "rent_roll"
#: Both were available. The derived figure is authoritative; the declared one is kept beside it.
BASIS_BOTH = "declared_and_derived"
#: Neither. **Not zero** — the difference matters and is the whole reason this constant exists.
BASIS_UNAVAILABLE = "unavailable"

BASIS_MEANING = {
    BASIS_DECLARED: "the deal supplied a blended figure and no lease detail was available to check it",
    BASIS_RENT_ROLL: "derived from the property's own lease records — in-place rent, recoveries and "
                     "concessions, each kept separate",
    BASIS_BOTH: "derived from lease records AND declared on the deal; both are reported so a "
                "disagreement between them is visible rather than resolved silently",
    BASIS_UNAVAILABLE: "no lease records and no declared figure — income is UNKNOWN, which is not the "
                       "same as zero and must not be underwritten as zero",
}

#: A disagreement below this is rounding and drafting noise; at or above it, someone should look.
#: Stated as a constant because a threshold buried in a comparison is a policy nobody can find.
MATERIAL_DISAGREEMENT_PCT = 5.0


def _num(v: Any) -> float | None:
    """Strictly numeric and finite. `bool` is rejected before `int` — `True` is not a rent of 1."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def from_rent_roll(rent_roll: dict | None, ner: dict | None = None) -> dict[str, Any]:
    """Turn a `rentroll.summarize()` result (+ optional `net_effective.roll_up()`) into proforma income.

    Returns the components separately rather than a single figure: base rent, recovery income and the
    concession load are three different things that a proforma must be able to treat differently."""
    if not rent_roll or not isinstance(rent_roll, dict):
        return {"available": False, "reason": "no rent roll supplied"}

    leases = rent_roll.get("lease_count")
    base = _num(rent_roll.get("base_rent_annual"))
    rec = _num(rent_roll.get("recoveries_annual"))

    # An empty rent roll is the dangerous case: every sum is legitimately 0.0, so the arithmetic
    # succeeds and the deal underwrites zero income as though it were measured.
    if not leases:
        return {"available": False,
                "reason": "the rent roll contains no active leases — income is UNKNOWN, not zero"}
    if base is None:
        return {"available": False, "reason": "rent roll carries no usable base rent"}

    out: dict[str, Any] = {
        "available": True,
        "lease_count": leases,
        "base_rent_annual": round(base, 2),
        # Kept SEPARATE from base rent on purpose — recoveries track the opex they reimburse, so
        # netting them destroys both the reimbursement and the opex ratio.
        "recovery_income_annual": round(rec or 0.0, 2),
        "potential_rent_annual": round(base + (rec or 0.0), 2),
        "occupancy_pct": rent_roll.get("occupancy_pct"),
        "walt_years": rent_roll.get("walt_years"),
        "occupied_sf": rent_roll.get("occupied_sf"),
        "vacant_sf": rent_roll.get("vacant_sf"),
    }

    if ner and isinstance(ner, dict):
        face = _num(ner.get("face_gpr_annual"))
        net = _num(ner.get("ner_gpr_annual_discounted")) or _num(ner.get("ner_gpr_annual"))
        if face is not None and net is not None:
            out["face_gpr_annual"] = round(face, 2)
            out["net_effective_gpr_annual"] = round(net, 2)
            out["concession_load_annual"] = round(face - net, 2)
            out["concession_load_pct"] = round(100 * (face - net) / face, 2) if face else None
        # Carried through by NAME, not collapsed to a count: a lease the maths could not use is a
        # lease somebody has to open, and a percentage cannot be opened.
        if ner.get("skipped"):
            out["leases_not_computable"] = ner["skipped"]
            out["leases_not_computable_count"] = ner.get("skipped_count", len(ner["skipped"]))
    return out


def resolve(declared_annual: Any = None, rent_roll: dict | None = None,
            ner: dict | None = None) -> dict[str, Any]:
    """The income a proforma should use, and an account of where it came from.

    Never silently prefers one source: when both exist the derived figure is used **and** the declared
    one is reported beside it with the gap between them."""
    derived = from_rent_roll(rent_roll, ner)
    dec = _num(declared_annual)

    if not derived.get("available") and dec is None:
        return {"basis": BASIS_UNAVAILABLE, "potential_rent_annual": None,
                "basis_meaning": BASIS_MEANING[BASIS_UNAVAILABLE],
                "reason": derived.get("reason", "no declared figure and no rent roll"),
                "declared_annual": None, "derived": None}

    if not derived.get("available"):
        return {"basis": BASIS_DECLARED, "potential_rent_annual": round(dec, 2),
                "basis_meaning": BASIS_MEANING[BASIS_DECLARED],
                "derived_unavailable_reason": derived.get("reason"),
                "declared_annual": round(dec, 2), "derived": None}

    use = derived["potential_rent_annual"]
    if dec is None:
        return {"basis": BASIS_RENT_ROLL, "potential_rent_annual": use,
                "basis_meaning": BASIS_MEANING[BASIS_RENT_ROLL],
                "declared_annual": None, "derived": derived}

    gap = use - dec
    pct = (100 * abs(gap) / dec) if dec else None
    return {
        "basis": BASIS_BOTH,
        "potential_rent_annual": use,          # the leases win — they are the asset's own record
        "basis_meaning": BASIS_MEANING[BASIS_BOTH],
        "declared_annual": round(dec, 2),
        "derived": derived,
        "declared_vs_derived": {
            "difference": round(gap, 2),
            "difference_pct": round(pct, 2) if pct is not None else None,
            # A boolean AND the threshold that produced it: a flag whose rule is invisible cannot be
            # argued with, and this one decides whether an underwriter re-cuts the deal.
            "material": bool(pct is not None and pct >= MATERIAL_DISAGREEMENT_PCT),
            "threshold_pct": MATERIAL_DISAGREEMENT_PCT,
            "note": "the rent roll is used; the declared figure is retained so the disagreement "
                    "survives rather than being resolved silently",
        },
    }
