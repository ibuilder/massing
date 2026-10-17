"""Rent roll & operating-asset analytics — the hold phase. Aggregates the `lease` module records
into occupancy, WALT, lease-expiration schedule and in-place income, so a built asset's *actual*
operations feed back into the proforma + appraisal (income approach). Pure over the lease dicts so
it's testable without a DB."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

ACTIVE_STATES = ("active", "holdover")


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def summarize(leases: list[dict], building_rentable_sf: float | None = None,
              as_of: date | None = None) -> dict[str, Any]:
    """leases: each lease's `data` dict + `workflow_state`. Returns the rent-roll summary.

    `building_rentable_sf` is the DENOMINATOR of every occupancy figure here, and it is optional
    because `project.dev_property["sqft"]` is a field nobody is obliged to fill. When it is absent
    the fallback is the leased area -- see `occupancy_basis` below, which exists so no caller has to
    guess whether a 100% figure means a full building or an unmeasured one.
    """
    today = as_of or date.today()
    active = [l for l in leases if (l.get("workflow_state") in ACTIVE_STATES)]
    rows, occupied_sf, base_rent, recoveries = [], 0.0, 0.0, 0.0
    walt_num, walt_den = 0.0, 0.0
    expirations: dict[int, dict[str, float]] = {}
    for l in active:
        d = l.get("data") or l
        sf = _num(d.get("rentable_sf"))
        rent = _num(d.get("base_rent_annual"))
        rec = _num(d.get("recovery_psf")) * sf
        occupied_sf += sf
        base_rent += rent
        recoveries += rec
        end = _parse_date(d.get("end_date"))
        months_remaining = 0.0
        if end:
            months_remaining = max(0.0, (end.year - today.year) * 12 + (end.month - today.month))
            yr = end.year
            e = expirations.setdefault(yr, {"count": 0, "sf": 0.0, "rent": 0.0})
            e["count"] += 1
            e["sf"] += sf
            e["rent"] += rent
        walt_num += sf * months_remaining
        walt_den += sf
        rows.append({
            "ref": l.get("ref"), "tenant": d.get("tenant"), "suite": d.get("suite"),
            "rentable_sf": round(sf), "base_rent_annual": round(rent, 2),
            "rent_psf": round(rent / sf, 2) if sf else 0.0, "lease_type": d.get("lease_type"),
            "start_date": d.get("start_date"), "end_date": d.get("end_date"),
            "months_remaining": round(months_remaining), "status": l.get("workflow_state"),
        })
    # RENTROLL-BASIS. The fallback stays and is now NAMED. When a project carries no rentable
    # building area the denominator becomes the numerator, so `occupancy_pct` is 100% whatever the
    # leases say -- measured with identical leases: a 20,000 sf building gives 30.0% with 14,000 sf
    # vacant, the same leases with the area unset give 100.0% with 0 vacant. Nothing downstream can
    # work that out, because a FULL building reports exactly the same four numbers: an equality
    # cannot separate two equal things, which is why this is stated rather than left to be derived.
    # The value is kept for the four consumers that already read it (the card, the rent-roll PDF
    # KPI, the income basis, the assistant snapshot) and every one of them now qualifies it --
    # WF-BASIS's shape: publish the base, do not silently change the answer.
    total_rentable = float(building_rentable_sf) if building_rentable_sf else occupied_sf
    occupancy_basis = "building" if building_rentable_sf else "leased"
    in_place_income = base_rent + recoveries
    return {
        "as_of": today.isoformat(),
        "lease_count": len(active),
        "total_rentable_sf": round(total_rentable),
        "occupied_sf": round(occupied_sf),
        "vacant_sf": round(max(0.0, total_rentable - occupied_sf)),
        "occupancy_pct": round(100 * occupied_sf / total_rentable, 1) if total_rentable else 0.0,
        "occupancy_basis": occupancy_basis,
        "building_rentable_sf": (round(float(building_rentable_sf))
                                 if building_rentable_sf else None),
        "occupancy_note": ("Occupancy is leased area / the project's rentable area."
                           if occupancy_basis == "building" else
                           "The project has NO rentable building area, so occupancy was computed "
                           "against the leased area and is 100% by construction. `vacant_sf` is 0 "
                           "for the same reason, not because the building is full. Set the "
                           "project's rentable SF for a real occupancy."),
        "base_rent_annual": round(base_rent, 2),
        "recoveries_annual": round(recoveries, 2),
        "in_place_gross_income": round(in_place_income, 2),
        "avg_rent_psf": round(base_rent / occupied_sf, 2) if occupied_sf else 0.0,
        "walt_years": round(walt_num / walt_den / 12, 2) if walt_den else 0.0,
        "expirations_by_year": {str(y): {"count": e["count"], "sf": round(e["sf"]),
                                         "rent": round(e["rent"], 2)}
                                for y, e in sorted(expirations.items())},
        "rows": sorted(rows, key=lambda r: (r.get("suite") or "")),
    }


def rent_roll(db, pid: str) -> dict[str, Any]:
    """Load the project's leases + building area and summarize."""
    from . import modules as me
    from .models import Project
    leases = me.list_records(db, "lease", pid, limit=100000) if "lease" in me.TABLES else []
    p = db.get(Project, pid)
    building_sf = _num((p.dev_property or {}).get("sqft")) if p else 0.0
    return summarize(leases, building_rentable_sf=building_sf or None)
