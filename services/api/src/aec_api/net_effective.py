"""CRE-NER (R20) — **net effective rent**: what a lease is actually worth after the concessions.

The `lease` module already stores everything this needs — term, base rent, escalation, free-rent
months, TI allowance — but every report so far has shown *face* rent. Face rent is the number a
broker quotes; net effective rent is the number underwriting, appraisal and agency lenders use,
because concessions come out of gross potential rent before effective gross income.

Two forms, both standard, both reported (they answer different questions):

* **Straight-line** — (total base rent over the term − landlord costs) ÷ term. The simple average
  a residential or quick-look analysis uses.
* **Discounted** — the level annual rent whose present value equals the present value of the actual
  net cash-flow stream. This is the commercial underwriting figure: it prices *when* the free rent
  and the TI cheque land, not just how big they are.

Landlord costs = free rent + tenant improvements + leasing commission. **Leasing commission is
never invented**: it is only included when the caller supplies a rate, and the result says whether
it was (`lc_included`). Everything is derived from stored fields — no estimates, no defaults
standing in for real data.
"""
from __future__ import annotations

from datetime import date
from typing import Any

_DEFAULT_DISCOUNT = 0.08          # annual, used for the discounted form unless the caller sets one


def _num(v: Any) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _term_months(lease: dict) -> int:
    start, end = _parse(lease.get("start_date")), _parse(lease.get("end_date"))
    if not start or not end or end <= start:
        return 0
    return max(1, (end.year - start.year) * 12 + (end.month - start.month))


def monthly_rents(base_annual: float, months: int, escalation_pct: float) -> list[float]:
    """The month-by-month base rent, escalating on each 12-month anniversary (the way a lease
    actually steps, not a smooth curve)."""
    out = []
    for m in range(months):
        year = m // 12
        out.append(base_annual / 12.0 * ((1.0 + escalation_pct / 100.0) ** year))
    return out


def lease_ner(lease: dict, discount_rate: float = _DEFAULT_DISCOUNT,
              lc_pct: float | None = None) -> dict[str, Any]:
    """Net effective rent for one lease, straight-line and discounted.

    `lc_pct` is the leasing commission as a percent of total base rent; omit it and the commission
    is excluded (and said so) rather than guessed at.
    """
    months = _term_months(lease)
    sf = _num(lease.get("rentable_sf"))
    base_annual = _num(lease.get("base_rent_annual"))
    esc = _num(lease.get("escalation_pct"))
    if months == 0 or base_annual <= 0:
        return {"tenant": lease.get("tenant"), "suite": lease.get("suite"),
                "term_months": months, "computable": False,
                "reason": "needs a start date, an end date and a base rent"}

    rents = monthly_rents(base_annual, months, esc)
    gross = sum(rents)
    free_months = int(_num(lease.get("free_rent_months")))
    free_months = max(0, min(free_months, months))
    free_rent = sum(rents[:free_months])                       # abated from the front, as written
    ti = _num(lease.get("ti_allowance_psf")) * sf
    lc = (gross * lc_pct / 100.0) if lc_pct is not None else 0.0
    landlord_costs = free_rent + ti + lc

    years = months / 12.0
    sl_annual = (gross - landlord_costs) / years

    # discounted: PV of the net stream ÷ PV of a $1/month annuity → the level equivalent rent
    r = (1.0 + discount_rate) ** (1.0 / 12.0) - 1.0
    net_flows = list(rents)
    for i in range(free_months):
        net_flows[i] = 0.0
    net_flows[0] -= (ti + lc)                                  # both land at commencement
    pv = sum(cf / ((1.0 + r) ** (i + 1)) for i, cf in enumerate(net_flows))
    annuity = sum(1.0 / ((1.0 + r) ** (i + 1)) for i in range(months))
    disc_annual = (pv / annuity) * 12.0 if annuity else 0.0

    return {
        "tenant": lease.get("tenant"), "suite": lease.get("suite"),
        "computable": True, "term_months": months, "rentable_sf": round(sf, 1),
        "face_rent_annual": round(base_annual, 2),
        "face_rent_psf": round(base_annual / sf, 2) if sf else None,
        "gross_rent_term": round(gross, 2),
        "free_rent": round(free_rent, 2), "free_rent_months": free_months,
        "ti_total": round(ti, 2), "leasing_commission": round(lc, 2),
        "lc_included": lc_pct is not None,
        "landlord_costs": round(landlord_costs, 2),
        "ner_annual_straight_line": round(sl_annual, 2),
        "ner_psf_straight_line": round(sl_annual / sf, 2) if sf else None,
        "ner_annual_discounted": round(disc_annual, 2),
        "ner_psf_discounted": round(disc_annual / sf, 2) if sf else None,
        "discount_rate": discount_rate,
        "concession_load_pct": round(100.0 * landlord_costs / gross, 1) if gross else 0.0,
        "face_to_ner_delta_pct": round(100.0 * (base_annual - disc_annual) / base_annual, 1)
                                 if base_annual else 0.0,
    }


def roll_up(leases: list[dict], discount_rate: float = _DEFAULT_DISCOUNT,
            lc_pct: float | None = None) -> dict[str, Any]:
    """Portfolio view: face GPR vs net effective GPR, the concession load, and the leases whose
    face rent overstates them most (the ones an underwriter re-cuts first). Leases missing the
    fields the maths needs are counted and named, never silently dropped."""
    rows = [lease_ner(x, discount_rate, lc_pct) for x in (leases or [])]
    ok = [r for r in rows if r.get("computable")]
    skipped = [{"tenant": r.get("tenant"), "suite": r.get("suite"), "reason": r.get("reason")}
               for r in rows if not r.get("computable")]
    face = sum(r["face_rent_annual"] for r in ok)
    ner = sum(r["ner_annual_discounted"] for r in ok)
    ner_sl = sum(r["ner_annual_straight_line"] for r in ok)
    costs = sum(r["landlord_costs"] for r in ok)
    gross = sum(r["gross_rent_term"] for r in ok)
    ok.sort(key=lambda r: -(r["face_rent_annual"] - r["ner_annual_discounted"]))
    return {
        "lease_count": len(ok), "skipped_count": len(skipped), "skipped": skipped[:50],
        "face_gpr_annual": round(face, 2),
        "ner_gpr_annual_discounted": round(ner, 2),
        "ner_gpr_annual_straight_line": round(ner_sl, 2),
        "concession_total_term": round(costs, 2),
        "concession_load_pct": round(100.0 * costs / gross, 1) if gross else 0.0,
        "face_to_ner_delta_annual": round(face - ner, 2),
        "face_to_ner_delta_pct": round(100.0 * (face - ner) / face, 1) if face else 0.0,
        "lc_included": lc_pct is not None,
        "discount_rate": discount_rate,
        "leases": ok,
        "note": ("Concessions (free rent + TI + any supplied leasing commission) are deducted "
                 "before effective income, the way agency underwriting does it. The discounted "
                 "figure prices WHEN the concession lands; the straight-line one does not. "
                 "Leasing commission is excluded unless a rate is supplied."),
    }


def from_project(db, pid: str, discount_rate: float = _DEFAULT_DISCOUNT,
                 lc_pct: float | None = None) -> dict[str, Any]:
    """The project's rent roll, net of concessions. Uses the SAME active-lease filter as
    `rentroll.summarize` (`ACTIVE_STATES`) so face GPR and net-effective GPR always describe the
    same set of leases — two surfaces disagreeing about which leases count is worse than either
    number being slightly off."""
    from . import modules as me
    from .rentroll import ACTIVE_STATES
    rows = me.list_records(db, "lease", pid, limit=100_000) if "lease" in me.TABLES else []
    leases = [r.get("data") or {} for r in rows if r.get("workflow_state") in ACTIVE_STATES]
    out = roll_up(leases, discount_rate, lc_pct)
    out["excluded_not_active"] = len(rows) - len(leases)
    return out
