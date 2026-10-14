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
    # Honour `cap_table`'s ownership rule rather than re-deriving one. A prospect drew a real
    # distribution share here — `share = lp_total * (commitment / lp_commit)` off a commitment nobody
    # had committed to — because these rows were filtered by CLASS and never by state.
    owning = [r for r in rows if r["counts_toward_ownership"]]
    lp = [r for r in owning if not _is_gp(r["investor_class"])]
    gp = [r for r in owning if _is_gp(r["investor_class"])]
    lp_commit = sum(r["commitment"] for r in lp)
    gp_commit = sum(r["commitment"] for r in gp)
    # no cap table -> nothing to allocate; return a clean zeroed scenario rather than a phantom split
    if lp_commit + gp_commit <= 0:
        return {
            "total_distributable": 0.0, "lp_contrib": 0.0, "gp_contrib": 0.0,
            "lp_distributions": 0.0, "gp_distributions": 0.0, "lp_irr": None, "gp_irr": None,
            "lp_equity_multiple": 0, "gp_equity_multiple": 0, "lp_unreturned": 0.0,
            "pref_rate": _DEFAULT_PREF, "style": "american", "periods": [], "per_investor": [],
            # `None`, not "committed": with no cap table there is no basis, and naming one would
            # describe a waterfall that did not run. Same rule as the zeroed figures beside it.
            "lp_basis": None, "gp_basis": None,
            "lp_commitment": 0.0, "gp_commitment": 0.0,
            "split_basis": "commitment", "split_mismatch": [],
            "note": "No investors with a commitment in the cap table — add investors to model distributions.",
        }
    # WHICH CAPITAL BASE THE WHOLE WATERFALL RUNS ON — and until WF-BASIS nothing said.
    #
    # The pref accrues on this figure, the return-of-capital tier returns it, and both IRRs and both
    # equity multiples are computed against it. The `or` falls back to the COMMITMENT when nothing
    # has been called, which is a defensible default and a silent one: measured on an $8m LP / $2m GP
    # cap table at a $20m exit, a deal with **nothing contributed** returns LP $18,302,056 / IRR
    # 17.99% / GP $1,697,944 — **byte-identical to the fully funded deal**. Half called gives LP
    # $17,151,028 / IRR 33.78% / GP $2,848,972: the same exit, $1.15m more promote.
    #
    # The two sides also fall back INDEPENDENTLY, so a cap table where the LPs have funded and the
    # GP has not produces one waterfall on two different bases. `lp_basis`/`gp_basis` are published
    # for exactly the reason `proforma/waterfall.run_waterfall` publishes `pref_accrual`: *"this used
    # to be unstated and unselectable … so it is now an explicit input, defaulted to the documented
    # behaviour and echoed in the result."* Same unstated deal term, one layer up.
    lp_called = sum(r["contributed"] for r in lp)
    gp_called = sum(r["contributed"] for r in gp)
    lp_contrib = lp_called or lp_commit
    gp_contrib = gp_called or gp_commit
    lp_basis = "contributed" if lp_called else "committed"
    gp_basis = "contributed" if gp_called else "committed"

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
    # THE SPLIT IS BY COMMITMENT, and the waterfall above may have run on CONTRIBUTED capital.
    #
    # That is two bases in one answer, and it is money: measured on LP Big ($8m committed, $1m
    # funded) and LP Small ($2m committed, $2m funded) at a $20m exit, the waterfall ran on
    # `lp_contrib` = $3m and then allocated the result 8:2, so **the LP who funded $1m takes
    # $13,490,617 and the one who funded $2m takes $3,372,654.**
    #
    # The allocation is NOT changed here. Which share a distribution follows is an operating-
    # agreement term — most split pro-rata to contributed capital, some to commitments — and
    # silently re-deciding it in a distribution calculator is not a correction, it is a different
    # deal. So both shares are published per investor, the disagreement is flagged, and the
    # decision is filed as WF-SPLIT for the user. *Show the working, withhold the verdict* — the
    # rule `proforma/authorityGate.ts` states for this family of card.
    def _slice(r: dict, total: float, commit: float, called: float) -> dict[str, Any]:
        """One investor's row. Shared by both classes so the two cannot drift apart — which is the
        defect one level up in this same function, where the money total and the schedule total had
        come to treat the same refusal differently."""
        return {
            "id": r["id"], "investor": r["investor"], "investor_class": r["investor_class"],
            "commitment": r["commitment"], "contributed": r["contributed"],
            "distribution": round(total * (r["commitment"] / commit), 2) if commit else 0.0,
            "commitment_share": round(r["commitment"] / commit, 6) if commit else 0.0,
            # `None`, not the commitment share, when nothing has been called on this side: there is
            # no contributed share to compare against, and substituting the other one would make
            # the two look agreed.
            "contributed_share": round(r["contributed"] / called, 6) if called else None,
        }

    per_investor = [_slice(r, lp_total, lp_commit, lp_called) for r in lp]
    per_investor += [_slice(r, gp_total, gp_commit, gp_called) for r in gp]
    # Investors whose two shares differ by more than a rounding tick. Named, because the per-investor
    # figure above rests on the one the waterfall did NOT use whenever this list is non-empty.
    split_mismatch = [
        {"investor": x["investor"], "commitment_share": x["commitment_share"],
         "contributed_share": x["contributed_share"]}
        for x in per_investor
        if x["contributed_share"] is not None
        and abs(x["contributed_share"] - x["commitment_share"]) > 1e-4
    ]

    return {
        "total_distributable": round(sum(distributable), 2),
        "lp_contrib": round(lp_contrib, 2), "gp_contrib": round(gp_contrib, 2),
        # `"contributed"` or `"committed"` — the one thing that distinguishes a deal nobody has
        # funded from one fully funded, whose outputs are otherwise identical.
        "lp_basis": lp_basis, "gp_basis": gp_basis,
        "lp_commitment": round(lp_commit, 2), "gp_commitment": round(gp_commit, 2),
        "split_basis": "commitment",
        "split_mismatch": split_mismatch,
        "lp_distributions": lp_total, "gp_distributions": gp_total,
        "lp_irr": wf["lp_irr"], "gp_irr": wf["gp_irr"],
        "lp_equity_multiple": wf["lp_equity_multiple"], "gp_equity_multiple": wf["gp_equity_multiple"],
        "lp_unreturned": wf["lp_unreturned"],
        "pref_rate": params["pref_rate"], "style": params["style"],
        "periods": wf["periods"],
        "per_investor": sorted(per_investor, key=lambda x: -x["distribution"]),
    }
