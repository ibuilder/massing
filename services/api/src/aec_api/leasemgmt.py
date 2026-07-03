"""Lease-management depth — the renewal/expiration pipeline, forward rent-escalation schedule
(compounded base rent), and CAM / expense-recovery reconciliation. Pure read-side aggregation over
the `lease` module; complements rentroll.py (which gives the point-in-time roll). No writes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

ACTIVE_STATES = ("active", "holdover", "renewed")
# lease types whose tenants reimburse operating expenses (drive CAM recovery)
RECOVERY_TYPES = ("NNN", "Modified Gross", "Percentage")
EXPIRY_BUCKETS = ((90, "<=90d"), (180, "<=180d"), (365, "<=365d"))


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _d(r: dict) -> dict:
    return r.get("data") or r


def renewal_pipeline(leases: list[dict], as_of: date | None = None) -> dict[str, Any]:
    """Expiring leases bucketed by window + holdover/expired, with renewal options and at-risk rent."""
    today = as_of or date.today()
    buckets = {label: {"count": 0, "rent": 0.0} for _, label in EXPIRY_BUCKETS}
    holdover = expired = options_count = 0
    at_risk_rent = 0.0
    rows = []
    for ls in leases:
        d = _d(ls)
        st = ls.get("workflow_state") or "draft"
        rent = _num(d.get("base_rent_annual"))
        end = _parse(d.get("end_date"))
        has_option = bool((d.get("renewal_options") or "").strip())
        if has_option:
            options_count += 1
        status = None
        if st == "holdover":
            holdover += 1
            status = "holdover"
            at_risk_rent += rent
        elif st in ("expired", "terminated"):
            expired += 1
            status = "expired"
        elif end and st in ACTIVE_STATES:
            days = (end - today).days
            if days < 0:
                status = "expired (active record)"
            else:
                for limit, label in EXPIRY_BUCKETS:
                    if days <= limit:
                        buckets[label]["count"] += 1
                        buckets[label]["rent"] = round(buckets[label]["rent"] + rent, 2)
                        if limit <= 365:
                            status = f"expiring {label}"
                        break
                if days <= 365:
                    at_risk_rent += rent
        if status:
            rows.append({
                "ref": ls.get("ref"), "tenant": d.get("tenant"), "suite": d.get("suite"),
                "end_date": d.get("end_date"), "base_rent_annual": rent,
                "renewal_options": d.get("renewal_options") or None,
                "has_option": has_option, "status": status,
            })
    return {
        "expiring": buckets, "holdover_count": holdover, "expired_count": expired,
        "options_outstanding": options_count, "at_risk_rent": round(at_risk_rent, 2),
        "rows": sorted(rows, key=lambda r: (r.get("end_date") or "9999")),
    }


def escalation_schedule(leases: list[dict], years: int = 5) -> dict[str, Any]:
    """Forward base-rent projection: each active lease compounded by its escalation_pct, plus the
    portfolio total per year-offset (year 0 = current base rent)."""
    years = max(1, min(int(years), 20))
    portfolio = [0.0] * (years + 1)
    rows = []
    for ls in leases:
        d = _d(ls)
        if (ls.get("workflow_state") or "draft") not in ACTIVE_STATES:
            continue
        base = _num(d.get("base_rent_annual"))
        esc = _num(d.get("escalation_pct")) / 100.0
        series = [round(base * ((1 + esc) ** y), 2) for y in range(years + 1)]
        for y in range(years + 1):
            portfolio[y] += series[y]
        rows.append({
            "ref": ls.get("ref"), "tenant": d.get("tenant"),
            "escalation_pct": _num(d.get("escalation_pct")),
            "base_rent_annual": base, "projected": series,
        })
    return {
        "years": years,
        "portfolio_by_year": [round(v, 2) for v in portfolio],
        "current_base_rent": round(portfolio[0], 2),
        "projected_base_rent": round(portfolio[years], 2),
        "rows": sorted(rows, key=lambda r: -r["base_rent_annual"]),
    }


def cam_reconciliation(leases: list[dict], recoverable_opex: float | None = None) -> dict[str, Any]:
    """Expense-recovery (CAM/NNN) reconciliation: budgeted recoveries (recovery_psf x rentable_sf)
    per recovery-type lease, the portfolio recoverable total, and — if a recoverable_opex pool is
    supplied — the recovery ratio and over/under-recovery gap."""
    by_type = {}
    recoverable_total = recoverable_sf = 0.0
    rows = []
    for ls in leases:
        d = _d(ls)
        if (ls.get("workflow_state") or "draft") not in ACTIVE_STATES:
            continue
        lt = (d.get("lease_type") or "(untyped)").strip() or "(untyped)"
        sf = _num(d.get("rentable_sf"))
        rec_psf = _num(d.get("recovery_psf"))
        recoverable = round(rec_psf * sf, 2)
        is_recovery = lt in RECOVERY_TYPES and recoverable > 0
        if is_recovery:
            recoverable_total += recoverable
            recoverable_sf += sf
            by_type[lt] = round(by_type.get(lt, 0.0) + recoverable, 2)
            rows.append({
                "ref": ls.get("ref"), "tenant": d.get("tenant"), "lease_type": lt,
                "rentable_sf": sf, "recovery_psf": rec_psf, "recoverable_income": recoverable,
            })
    out = {
        "recoverable_income": round(recoverable_total, 2),
        "recoverable_sf": round(recoverable_sf, 2),
        "by_lease_type": by_type,
        "rows": sorted(rows, key=lambda r: -r["recoverable_income"]),
    }
    if recoverable_opex is not None:
        pool = _num(recoverable_opex)
        gap = round(recoverable_total - pool, 2)
        out["recoverable_opex"] = round(pool, 2)
        out["recovery_ratio"] = round(recoverable_total / pool, 3) if pool else None
        out["over_recovery"] = gap if gap > 0 else 0.0      # billed more than the pool
        out["under_recovery"] = -gap if gap < 0 else 0.0    # leakage: opex not recovered
    return out


def lease_management(db, pid: str, years: int = 5, recoverable_opex: float | None = None) -> dict[str, Any]:
    from . import modules as me
    leases = me.list_records(db, "lease", pid, limit=100000) if "lease" in me.TABLES else []
    return {
        "lease_count": len(leases),
        "renewals": renewal_pipeline(leases),
        "escalations": escalation_schedule(leases, years),
        "cam": cam_reconciliation(leases, recoverable_opex),
    }
