"""Distribution / equity-waterfall scenarios on the live investor cap table. Reuses the proforma
waterfall engine (pref -> return of capital -> IRR-hurdle promote tiers) at the LP/GP class level,
then allocates each side's take pro-rata across the actual `investor` records by commitment. Lets a
sponsor model "if we distribute $X (or this series), who gets what." Pure read-side; no writes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .proforma.waterfall import run_waterfall

# sensible JV defaults when the proforma scenario has no waterfall block
_DEFAULT_TIERS = [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}, {"hurdle": None, "lp": 0.8, "gp": 0.2}]
_DEFAULT_PREF = 0.08


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse(s: Any, fallback: date) -> date:
    if not s:
        return fallback
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return fallback


def _is_gp(cls: str) -> bool:
    return "GP" in (cls or "").upper()


def _wf_params(db, pid: str, overrides: dict | None) -> dict:
    """Pull pref_rate / tiers / style / clawback from the latest proforma scenario, then apply overrides."""
    from .marketing import _latest_scenario
    params = {"pref_rate": _DEFAULT_PREF, "tiers": _DEFAULT_TIERS, "style": "american", "clawback": False}
    s = _latest_scenario(db, pid)
    wf = (s.assumptions or {}).get("waterfall") if s else None
    if isinstance(wf, dict):
        if wf.get("pref_rate") is not None:
            params["pref_rate"] = _num(wf["pref_rate"])
        if wf.get("tiers"):
            params["tiers"] = wf["tiers"]
        if wf.get("style"):
            params["style"] = wf["style"]
        params["clawback"] = bool(wf.get("clawback", False))
    for k in ("pref_rate", "tiers", "style", "clawback"):
        if overrides and overrides.get(k) is not None:
            params[k] = overrides[k]
    return params


def scenario(db, pid: str, body: dict | None = None) -> dict[str, Any]:
    """Run a distribution scenario through the equity waterfall and allocate to investors.

    body: { distributable: [..], dates: [contribution_date, d1, d2, ...] }  (dates len = distributable+1)
          or { exit_amount, contribution_date, exit_date }  (single distribution).
    Optional waterfall overrides: pref_rate, tiers, style, clawback."""
    from . import capital
    from . import modules as me
    body = body or {}
    investors = me.list_records(db, "investor", pid, limit=100000) if "investor" in me.TABLES else []
    ct = capital.cap_table(investors)
    rows = ct["rows"]
    lp = [r for r in rows if not _is_gp(r["investor_class"])]
    gp = [r for r in rows if _is_gp(r["investor_class"])]
    lp_commit = sum(r["commitment"] for r in lp)
    gp_commit = sum(r["commitment"] for r in gp)
    # no cap table -> nothing to allocate; return a clean zeroed scenario rather than a phantom split
    if lp_commit + gp_commit <= 0:
        return {
            "total_distributable": 0.0, "lp_contrib": 0.0, "gp_contrib": 0.0,
            "lp_distributions": 0.0, "gp_distributions": 0.0, "lp_irr": None, "gp_irr": None,
            "lp_equity_multiple": 0, "gp_equity_multiple": 0, "lp_unreturned": 0.0,
            "pref_rate": _DEFAULT_PREF, "style": "american", "periods": [], "per_investor": [],
            "note": "No investors with a commitment in the cap table — add investors to model distributions.",
        }
    # contributed basis (fall back to commitment if nothing has been called yet)
    lp_contrib = sum(r["contributed"] for r in lp) or lp_commit
    gp_contrib = sum(r["contributed"] for r in gp) or gp_commit

    today = date.today()
    if body.get("distributable"):
        distributable = [_num(x) for x in body["distributable"]]
        raw_dates = body.get("dates") or []
        dates = [_parse(d, today) for d in raw_dates]
        if len(dates) < len(distributable) + 1:
            # synthesize annual periods from a contribution date if dates are short
            base = dates[0] if dates else _parse(body.get("contribution_date"), today)
            dates = [date(base.year + i, base.month, min(base.day, 28)) for i in range(len(distributable) + 1)]
    else:
        amt = _num(body.get("exit_amount"))
        c0 = _parse(body.get("contribution_date"), date(today.year - 5, today.month, min(today.day, 28)))
        d1 = _parse(body.get("exit_date"), today)
        distributable = [amt]
        dates = [c0, d1]

    params = _wf_params(db, pid, body)
    wf = run_waterfall(distributable, dates, lp_contrib, gp_contrib,
                       params["pref_rate"], params["tiers"], params["style"], params["clawback"])

    lp_total = wf["lp_distributions"]
    gp_total = wf["gp_distributions"]
    per_investor = []
    for r in lp:
        share = lp_total * (r["commitment"] / lp_commit) if lp_commit else 0.0
        per_investor.append({"id": r["id"], "investor": r["investor"], "investor_class": r["investor_class"],
                             "commitment": r["commitment"], "distribution": round(share, 2)})
    for r in gp:
        share = gp_total * (r["commitment"] / gp_commit) if gp_commit else 0.0
        per_investor.append({"id": r["id"], "investor": r["investor"], "investor_class": r["investor_class"],
                             "commitment": r["commitment"], "distribution": round(share, 2)})

    return {
        "total_distributable": round(sum(distributable), 2),
        "lp_contrib": round(lp_contrib, 2), "gp_contrib": round(gp_contrib, 2),
        "lp_distributions": lp_total, "gp_distributions": gp_total,
        "lp_irr": wf["lp_irr"], "gp_irr": wf["gp_irr"],
        "lp_equity_multiple": wf["lp_equity_multiple"], "gp_equity_multiple": wf["gp_equity_multiple"],
        "lp_unreturned": wf["lp_unreturned"],
        "pref_rate": params["pref_rate"], "style": params["style"],
        "periods": wf["periods"],
        "per_investor": sorted(per_investor, key=lambda x: -x["distribution"]),
    }
