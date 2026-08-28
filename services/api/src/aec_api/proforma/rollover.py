"""PF-ROLLOVER — what a lease expiry actually costs.

`rentroll.summarize()` gives expirations by year and `leasemgmt.renewal_pipeline()` buckets them with
the rent at risk. Both answer *when* leases expire. Neither answers **what rolling them costs**, and
that is the number an underwriter needs: a rollover is not an event on a calendar, it is downtime
plus tenant improvements plus a leasing commission, weighted by whether the tenant actually renews.

Without it a proforma treats in-place rent as continuing forever. That is not a small error — it is
**strictly optimistic in three directions at once** (no vacancy gap, no TI, no commission) and it
compounds every time a lease turns over during the hold.

## The refusals, and why each is the difference between a model and a guess

1. **Downtime is not optional.** A rollover model with no downtime produces continuous occupancy —
   better than reality, and it reads as a *modelling result* rather than as an omission. If it is not
   stated, this refuses rather than defaulting to zero. Zero downtime is a legitimate assumption
   (pre-leased, or a renewal-only building) but it has to be *chosen*.

2. **Renewal probability is not optional either, for the same reason inverted.** Assuming every
   tenant renews removes the rollover risk this module exists to price. Assuming none renew overstates
   cost. Both are defensible inputs; neither is a defensible default.

3. **Downtime applies ONLY to the non-renewal branch.** A renewing tenant does not vacate. Applying
   downtime to the whole expiry double-counts a gap that never happens — the most common way a
   rollover model overstates cost, and it hides inside a plausible-looking total.

4. **A lease with no end date cannot be rolled, and is NAMED.** Dropping it silently shrinks the
   rollover exposure and makes the deal look better; a named lease is one somebody can go and fix.

5. **The expected-value split is reported, not just the total.** `p x renewal + (1-p) x new` is a
   blend of two futures, and a committee that cannot see the two branches cannot argue with the
   weighting.

Pure over lease dicts and a stated assumption set — no DB, deterministic, unit-testable.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: Returned instead of a schedule when the caller has not stated the assumptions that decide the
#: answer. Refusing is the point: every one of these has a value that looks reasonable and quietly
#: removes the risk being priced.
STATUS_OK = "priced"
STATUS_MISSING_ASSUMPTION = "assumptions_incomplete"

REQUIRED = ("renewal_probability", "downtime_months")

REQUIRED_WHY = {
    "renewal_probability": "assuming every tenant renews removes the rollover risk entirely; "
                           "assuming none overstates it. Both are legitimate inputs, neither is a "
                           "legitimate default",
    "downtime_months": "a rollover with no vacancy gap is strictly better than reality and reads as "
                       "a modelling result rather than an omission. Zero is allowed — but chosen",
}


def _num(v: Any) -> float | None:
    """Strictly numeric and finite. `bool` is rejected before `int` — `True` is not a probability."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.fromisoformat(v.strip()[:10]).date()
    except ValueError:
        return None


def _assumptions(a: dict | None) -> tuple[dict, list[str]]:
    """Validate the stated assumptions. Returns (clean, missing)."""
    a = a or {}
    clean: dict[str, float] = {}
    missing: list[str] = []
    for k in REQUIRED:
        v = _num(a.get(k))
        if v is None:
            missing.append(k)
        else:
            clean[k] = v
    p = clean.get("renewal_probability")
    if p is not None and not (0.0 <= p <= 1.0):
        missing.append("renewal_probability")      # out of range is *unstated*, not clamped
        clean.pop("renewal_probability", None)
    if clean.get("downtime_months", 0.0) < 0:
        missing.append("downtime_months")
        clean.pop("downtime_months", None)
    # Optional, genuinely defaultable — a zero TI allowance or commission is a real, common deal term
    # and carries no hidden optimism, unlike downtime or renewal probability.
    for k, d in (("ti_new_psf", 0.0), ("ti_renewal_psf", 0.0),
                 ("lc_new_pct", 0.0), ("lc_renewal_pct", 0.0),
                 ("market_rent_psf", 0.0), ("new_term_years", 5.0)):
        v = _num(a.get(k))
        clean[k] = d if v is None else v
    return clean, sorted(set(missing))


def price_expiry(lease: dict, a: dict) -> dict[str, Any]:
    """The expected cost of rolling ONE lease, split into its two futures."""
    d = lease.get("data") or lease
    sf = _num(d.get("rentable_sf")) or 0.0
    in_place = _num(d.get("base_rent_annual")) or 0.0
    p = a["renewal_probability"]
    dt = a["downtime_months"]

    market_rent = (a["market_rent_psf"] * sf) if a["market_rent_psf"] else in_place
    term = a["new_term_years"]

    # Renewal branch: no vacancy, lighter TI, lower commission.
    ti_renew = a["ti_renewal_psf"] * sf
    lc_renew = a["lc_renewal_pct"] * market_rent * term
    renew_cost = ti_renew + lc_renew

    # New-tenant branch: the vacancy gap is HERE and only here.
    ti_new = a["ti_new_psf"] * sf
    lc_new = a["lc_new_pct"] * market_rent * term
    downtime_rent_loss = (in_place / 12.0) * dt
    new_cost = ti_new + lc_new + downtime_rent_loss

    return {
        "tenant": d.get("tenant"), "suite": d.get("suite"), "ref": lease.get("ref"),
        "end_date": d.get("end_date"), "rentable_sf": round(sf, 2),
        "in_place_rent_annual": round(in_place, 2),
        "market_rent_annual": round(market_rent, 2),
        "renewal": {"probability": p, "ti": round(ti_renew, 2), "lc": round(lc_renew, 2),
                    "downtime_months": 0.0, "downtime_rent_loss": 0.0,
                    "total": round(renew_cost, 2),
                    "note": "a renewing tenant does not vacate, so no downtime applies to this branch"},
        "new_tenant": {"probability": round(1.0 - p, 4), "ti": round(ti_new, 2),
                       "lc": round(lc_new, 2), "downtime_months": dt,
                       "downtime_rent_loss": round(downtime_rent_loss, 2),
                       "total": round(new_cost, 2)},
        "expected_cost": round(p * renew_cost + (1.0 - p) * new_cost, 2),
        "expected_downtime_months": round((1.0 - p) * dt, 2),
    }


def schedule(leases: list[dict], assumptions: dict | None = None,
             as_of: date | None = None, horizon_years: int = 10) -> dict[str, Any]:
    """Rollover cost by expiry year across the hold.

    `leases` are `lease` module records. `assumptions` must state `renewal_probability` and
    `downtime_months`; everything else has a defensible default."""
    a, missing = _assumptions(assumptions)
    if missing:
        return {"status": STATUS_MISSING_ASSUMPTION,
                "missing": missing,
                "why": {k: REQUIRED_WHY[k] for k in missing if k in REQUIRED_WHY},
                "note": "no rollover schedule was produced. Defaulting these would price a deal with "
                        "no vacancy gap or no rollover risk, which is strictly optimistic and "
                        "indistinguishable in the output from a deal that genuinely has neither.",
                "by_year": {}, "total_expected_cost": None}

    today = as_of or date.today()
    horizon = today.year + horizon_years
    by_year: dict[str, dict] = {}
    rows: list[dict] = []
    undateable: list[dict] = []

    # ONE DEFINITION OF "IN PLACE", IMPORTED RATHER THAN RESTATED. `rentroll.summarize()` — which
    # this module's own docstring names as its peer — counts a lease as income only when its
    # `workflow_state` is active or holdover. This engine had no state filter at all, so a DRAFT
    # lease (a negotiation that may never sign) produced no income and yet a full rollover cost.
    #
    # Measured: two draft leases returned `expiries_priced: 2, total_expected_cost: 799816.67`
    # while `/proforma/income-basis` on the same project reported an empty rent roll. A cost with no
    # matching income is the asymmetry that makes a model wrong, and this module refuses three
    # smaller ones already.
    #
    # NAMED, NOT DROPPED, for the reason stated below about undateable leases: excluding a lease
    # shrinks the exposure and makes the deal look BETTER, which is the direction an omission must
    # never fail in silently.
    from ..rentroll import ACTIVE_STATES

    not_in_place: list[dict] = []
    in_place = []
    for ls in leases or []:
        st = ls.get("workflow_state")
        if st is not None and st not in ACTIVE_STATES:
            not_in_place.append({"ref": ls.get("ref"), "tenant": (ls.get("data") or ls).get("tenant"),
                                 "suite": (ls.get("data") or ls).get("suite"), "workflow_state": st,
                                 "reason": f"not in place ({st}) — no income, so no rollover to price"})
            continue
        in_place.append(ls)

    for ls in in_place:
        d = ls.get("data") or ls
        end = _parse(d.get("end_date"))
        if end is None:
            # Named, not dropped: a silently-skipped lease shrinks the rollover exposure and makes
            # the deal look better, which is the direction an omission must never fail in.
            undateable.append({"ref": ls.get("ref"), "tenant": d.get("tenant"),
                               "suite": d.get("suite"), "reason": "no usable end_date"})
            continue
        if end.year > horizon or end < today:
            continue
        row = price_expiry(ls, a)
        rows.append(row)
        y = by_year.setdefault(str(end.year), {"expiries": 0, "expiring_rent": 0.0,
                                               "expected_cost": 0.0,
                                               "expected_downtime_months": 0.0, "sf": 0.0})
        y["expiries"] += 1
        y["expiring_rent"] += row["in_place_rent_annual"]
        y["expected_cost"] += row["expected_cost"]
        y["expected_downtime_months"] += row["expected_downtime_months"]
        y["sf"] += row["rentable_sf"]

    for y in by_year.values():
        for k in ("expiring_rent", "expected_cost", "expected_downtime_months", "sf"):
            y[k] = round(y[k], 2)

    return {
        "status": STATUS_OK,
        "as_of": today.isoformat(),
        "horizon_year": horizon,
        "assumptions_used": a,
        "expiries_priced": len(rows),
        "by_year": dict(sorted(by_year.items())),
        "total_expected_cost": round(sum(r["expected_cost"] for r in rows), 2),
        "total_expected_downtime_months": round(sum(r["expected_downtime_months"] for r in rows), 2),
        "rows": rows,
        "leases_without_end_date": undateable,
        "leases_not_in_place": not_in_place,
        "note": "expected cost = p x renewal + (1-p) x new tenant. Downtime is applied to the "
                "new-tenant branch ONLY — a renewing tenant does not vacate, and charging the gap "
                "to both branches is the most common way a rollover total is overstated.",
    }
