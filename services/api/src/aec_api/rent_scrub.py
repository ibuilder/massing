"""CRE-RRSCRUB (R20) — **reconcile the rent roll against the income statement.**

Two structured sources describe the same property from different directions: the rent roll says who
is in place and for how much, the T-12 says what was actually collected. Where they disagree is
where the diligence is. Industry practice treats a scheduled-rent-versus-gross-potential-rent gap
of more than ~5% as an item to chase rather than a rounding difference.

The design rule that matters here: **a check that cannot run says so.** Every check declares the
inputs it needs, and when they are absent it returns `applicable: false` with the reason instead of
quietly passing. A scrub that reports "no findings" because half its inputs were missing is worse
than no scrub — it launders absent data into apparent confidence.

Composes directly with the shipped pieces: leases come from the `lease` module (the same
active-state filter the rent roll uses), the income side comes from CRE-T12's normalized output.
"""
from __future__ import annotations

from datetime import date
from typing import Any

SCHEDULED_VS_GPR_TOLERANCE_PCT = 5.0     # industry-standard diligence threshold


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


def _check(name: str, applicable: bool, *, needs: str = "", severity: str = "info",
           finding: str = "", passed: bool | None = None, **extra) -> dict[str, Any]:
    if not applicable:
        return {"check": name, "applicable": False, "needs": needs,
                "finding": f"not run — {needs}"}
    return {"check": name, "applicable": True, "passed": bool(passed),
            "severity": severity if not passed else "ok", "finding": finding, **extra}


def scrub(leases: list[dict], income: dict | None = None,
          units: list[dict] | None = None) -> dict[str, Any]:
    """Reconcile the rent roll against the income statement and the unit inventory.

    `leases`  — lease `data` dicts (tenant, unit/suite, base_rent_annual, start/end dates).
    `income`  — optional normalized income, e.g. CRE-T12's `by_category`-derived figures:
                {gross_potential_rent, vacancy_loss, concessions, bad_debt, effective_income,
                 prior_bad_debt, prior_occupancy_pct}.
    `units`   — optional unit inventory: [{unit, occupied: bool, receivable: float,
                arrears_by_month: [..]}].
    """
    leases = leases or []
    income = income or {}
    checks: list[dict[str, Any]] = []

    scheduled = sum(_num(x.get("base_rent_annual")) for x in leases)
    gpr = _num(income.get("gross_potential_rent"))

    # --- 1) scheduled rent vs gross potential rent --------------------------------------------------
    if leases and gpr > 0:
        delta = scheduled - gpr
        pct = abs(delta) / gpr * 100.0
        checks.append(_check(
            "scheduled_vs_gpr", True,
            passed=pct <= SCHEDULED_VS_GPR_TOLERANCE_PCT,
            severity="high",
            finding=(f"rent roll schedules ${scheduled:,.0f} against ${gpr:,.0f} of gross potential "
                     f"rent — {pct:.1f}% apart"),
            scheduled_rent=round(scheduled, 2), gross_potential_rent=round(gpr, 2),
            delta=round(delta, 2), variance_pct=round(pct, 2),
            tolerance_pct=SCHEDULED_VS_GPR_TOLERANCE_PCT))
    else:
        checks.append(_check("scheduled_vs_gpr", False,
                             needs="leases with base_rent_annual AND income.gross_potential_rent"))

    # --- 2) occupied units with no lease on file ----------------------------------------------------
    if units:
        keyed = {str(x.get("suite") or x.get("unit") or "").strip().lower() for x in leases}
        keyed.discard("")
        orphans = [u.get("unit") for u in units
                   if u.get("occupied") and str(u.get("unit") or "").strip().lower() not in keyed]
        checks.append(_check(
            "occupied_without_lease", True, passed=not orphans, severity="high",
            finding=(f"{len(orphans)} occupied unit(s) have no lease record" if orphans
                     else "every occupied unit has a lease record"),
            units=orphans[:50]))
    else:
        checks.append(_check("occupied_without_lease", False,
                             needs="a unit inventory with {unit, occupied}"))

    # --- 3) vacant units carrying a receivable ------------------------------------------------------
    if units and any("receivable" in u for u in units):
        bad = [{"unit": u.get("unit"), "receivable": round(_num(u.get("receivable")), 2)}
               for u in units if not u.get("occupied") and _num(u.get("receivable")) > 0]
        checks.append(_check(
            "vacant_with_receivable", True, passed=not bad, severity="medium",
            finding=(f"{len(bad)} vacant unit(s) still carry a receivable — move-out processing "
                     "may be incomplete" if bad else "no vacant unit carries a receivable"),
            units=bad[:50]))
    else:
        checks.append(_check("vacant_with_receivable", False,
                             needs="a unit inventory with {occupied, receivable}"))

    # --- 4) arrears rising every month ---------------------------------------------------------------
    series_units = [u for u in (units or []) if len(u.get("arrears_by_month") or []) >= 3]
    if series_units:
        rising = []
        for u in series_units:
            s = [_num(x) for x in u["arrears_by_month"]]
            if all(b > a for a, b in zip(s, s[1:])) and s[-1] > 0:
                rising.append({"unit": u.get("unit"), "arrears": [round(x, 2) for x in s]})
        checks.append(_check(
            "arrears_rising", True, passed=not rising, severity="medium",
            finding=(f"{len(rising)} unit(s) show arrears rising every month — collections may be "
                     "misapplied or a payment plan is missing" if rising
                     else "no unit shows monotonically rising arrears"),
            units=rising[:50]))
    else:
        checks.append(_check("arrears_rising", False,
                             needs="a unit inventory with >=3 months of arrears_by_month"))

    # --- 5) bad debt rising against flat occupancy --------------------------------------------------
    bd, prior_bd = _num(income.get("bad_debt")), _num(income.get("prior_bad_debt"))
    occ, prior_occ = _num(income.get("occupancy_pct")), _num(income.get("prior_occupancy_pct"))
    if bd and prior_bd and occ and prior_occ:
        worsening = bd > prior_bd * 1.10 and abs(occ - prior_occ) <= 1.0
        checks.append(_check(
            "bad_debt_vs_occupancy", True, passed=not worsening, severity="high",
            finding=(f"bad debt rose from ${prior_bd:,.0f} to ${bd:,.0f} while occupancy held at "
                     f"{occ:.1f}% — the tenant base is weakening before the rent roll shows it"
                     if worsening else "bad debt is not rising against flat occupancy"),
            bad_debt=round(bd, 2), prior_bad_debt=round(prior_bd, 2),
            occupancy_pct=occ, prior_occupancy_pct=prior_occ))
    else:
        checks.append(_check("bad_debt_vs_occupancy", False,
                             needs="income.bad_debt + prior_bad_debt + occupancy_pct + prior_occupancy_pct"))

    # --- 6) leases whose stated rent contradicts the executed terms ---------------------------------
    mismatched = [{"tenant": x.get("tenant"), "suite": x.get("suite"),
                   "stated": round(_num(x.get("base_rent_annual")), 2),
                   "executed": round(_num(x.get("executed_rent_annual")), 2)}
                  for x in leases
                  if _num(x.get("executed_rent_annual")) > 0
                  and abs(_num(x.get("base_rent_annual")) - _num(x.get("executed_rent_annual"))) > 1.0]
    has_executed = any(_num(x.get("executed_rent_annual")) > 0 for x in leases)
    if has_executed:
        checks.append(_check(
            "rent_vs_executed_terms", True, passed=not mismatched, severity="high",
            finding=(f"{len(mismatched)} lease(s) state a rent that differs from the executed terms"
                     if mismatched else "stated rents match the executed terms"),
            leases=mismatched[:50]))
    else:
        checks.append(_check("rent_vs_executed_terms", False,
                             needs="leases carrying executed_rent_annual to compare against"))

    # --- 7) expired leases still counted as in place ------------------------------------------------
    today = date.today()
    expired = [{"tenant": x.get("tenant"), "suite": x.get("suite"), "end_date": x.get("end_date")}
               for x in leases if (_parse(x.get("end_date")) or today) < today]
    checks.append(_check(
        "expired_still_active", bool(leases), passed=not expired, severity="medium",
        needs="leases with end dates",
        finding=(f"{len(expired)} active lease(s) ended before today — holdover or a stale roll"
                 if expired else "no active lease is past its end date"),
        leases=expired[:50]))

    ran = [c for c in checks if c["applicable"]]
    failed = [c for c in ran if not c.get("passed")]
    return {
        "checks": checks,
        "counts": {"total": len(checks), "ran": len(ran), "not_applicable": len(checks) - len(ran),
                   "passed": len(ran) - len(failed), "failed": len(failed)},
        "findings": failed,
        "clean": bool(ran) and not failed,
        "coverage_note": (f"{len(ran)} of {len(checks)} checks could run; "
                          f"{len(checks) - len(ran)} lacked inputs and are reported as not-run, "
                          "never as passing."),
    }


def from_project(db, pid: str, income: dict | None = None,
                 units: list[dict] | None = None) -> dict[str, Any]:
    """Scrub the project's ACTIVE leases (the same set the rent roll reports) against the supplied
    income statement and unit inventory."""
    from . import modules as me
    from .rentroll import ACTIVE_STATES
    rows = me.list_records(db, "lease", pid, limit=100_000) if "lease" in me.TABLES else []
    leases = [r.get("data") or {} for r in rows if r.get("workflow_state") in ACTIVE_STATES]
    out = scrub(leases, income, units)
    out["lease_count"] = len(leases)
    out["excluded_not_active"] = len(rows) - len(leases)
    return out
