"""Earned Value Management (EVM) — one ANSI/EIA-748-aligned metric set.

The platform already had two disconnected halves: schedule **earned value** (EV = % complete × budget,
in `routers/schedule.py`) and cost **actuals** by cost code (`project_budget.py` / `cost.py`). Neither
computed the join, so there was no CPI, CV, or standards-based forecast. This engine joins them **by
cost code (the control account)** and produces the full set:

- Measured: PV (BCWS), EV (BCWP), AC (ACWP), BAC.
- Variances / indices: CV = EV−AC, SV = EV−PV, CPI = EV/AC, SPI = EV/PV, % complete, % spent.
- Forecast family (E2): the four canonical EACs, ETC, VAC, and TCPI to BAC and to EAC — shown together,
  since the "best" EAC is stage-dependent (see the roadmap note / PMC study), not a single formula.

EV here uses the schedule-% measurement method; richer methods (0/100, 50/50, units-complete, …) and the
time-based Earned Schedule extension come in later phases. Coordinates: dollars; a control account is a
cost-code grouping (the closest thing the data model has to an EIA-748 control account).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

_PERIOD_DAYS = {"week": 7.0, "month": 30.44}


def _n(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _d(s: Any):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def index_band(idx: float | None) -> str:
    """Traffic-light band for a performance index (CPI/SPI). Government scrutiny starts < 0.95."""
    if idx is None:
        return "no_data"
    if idx >= 1.0:
        return "good"
    if idx >= 0.95:
        return "acceptable"
    if idx >= 0.90:
        return "concerning"
    return "critical"


def _measured_fraction(d: dict) -> tuple[float, str]:
    """The EARNED fraction of an activity's budget under its EV measurement method (rule of credit):
    percent (%), 0-100 (all-or-nothing), 50-50 (half at start), units (units_complete/units_total),
    milestone (≈percent), loe (level of effort — corrected to EV=PV by the caller)."""
    method = (d.get("ev_method") or "percent").lower()
    pct = max(0.0, min(100.0, _n(d.get("percent")))) / 100.0
    if method == "0-100":
        return (1.0 if pct >= 1.0 else 0.0), method
    if method == "50-50":
        return (1.0 if pct >= 1.0 else (0.5 if pct > 0 else 0.0)), method
    if method == "units":
        ut = _n(d.get("units_total"))
        return (max(0.0, min(1.0, _n(d.get("units_complete")) / ut)) if ut > 0 else pct), method
    return pct, method                                # percent / milestone / loe → the % fraction


def _planned_fraction(data: dict, today: date) -> float:
    """Linear planned fraction of an activity's budget earned by `today` (BCWS spread).
    (A true non-linear time-phased PV curve arrives with Earned Schedule, phase E3.)"""
    s = _d(data.get("start")) or _d(data.get("actual_start"))
    f = _d(data.get("finish")) or _d(data.get("actual_finish"))
    if s and f and f > s:
        return max(0.0, min(1.0, (today - s).days / (f - s).days))
    if f:
        return 1.0 if today >= f else 0.0
    return 0.0


def forecasts(bac: float, ev: float, ac: float, cpi: float | None, spi: float | None) -> dict[str, Any]:
    """The EAC / ETC / VAC / TCPI family (E2). Every EAC variant assumes something different about how
    the remaining work will perform; we return them side-by-side rather than pick one."""
    remaining = bac - ev
    out: dict[str, Any] = {}
    # EAC variants
    eac_cpi = round(bac / cpi, 2) if cpi else None                       # remaining at current cost efficiency
    eac_plan = round(ac + remaining, 2)                                  # remaining at plan (variance was one-off)
    eac_cpi_spi = round(ac + remaining / (cpi * spi), 2) if (cpi and spi) else None  # cost+schedule drag
    out["eac"] = {
        "cpi": eac_cpi,               # BAC / CPI  — the default
        "at_plan": eac_plan,          # AC + (BAC − EV)
        "cpi_spi": eac_cpi_spi,       # AC + (BAC − EV) / (CPI × SPI) — pessimistic, common in construction
    }
    # the working EAC we forecast against: CPI×SPI if available (captures schedule-driven cost), else CPI
    working_eac = eac_cpi_spi or eac_cpi or eac_plan
    out["eac_working"] = round(working_eac, 2) if working_eac is not None else None
    out["etc"] = round(working_eac - ac, 2) if working_eac is not None else None   # EAC − AC
    out["vac"] = round(bac - working_eac, 2) if working_eac is not None else None   # BAC − EAC (neg = overrun)
    # TCPI — the efficiency the remaining work must achieve
    tcpi_bac = round(remaining / (bac - ac), 3) if (bac - ac) else None
    tcpi_eac = round(remaining / (working_eac - ac), 3) if (working_eac and (working_eac - ac)) else None
    out["tcpi_bac"] = tcpi_bac        # to finish within budget
    out["tcpi_eac"] = tcpi_eac        # to finish within the working forecast
    # a TCPI far above CPI (~>1.10) is a structural warning: the team must suddenly outperform its history
    out["tcpi_warning"] = bool(tcpi_bac and cpi and tcpi_bac - cpi > 0.10)
    # stage-adaptive forecast guidance — a construction-forecasting study found the most accurate method
    # is schedule-based (Earned Schedule) early and cost-efficiency-based (CPI) late; methods barely
    # diverge before ~70% complete, so early cost EACs are volatile.
    pct = (ev / bac * 100) if bac else 0.0
    if pct < 25:
        out["recommended"] = {"stage": "early", "recommended_eac": "cpi_spi",
                              "guidance": "Early (<25%): trust Earned Schedule / SPI(t) — cost EAC is volatile."}
    elif pct < 55:
        out["recommended"] = {"stage": "mid", "recommended_eac": "cpi_spi",
                              "guidance": "Mid (25–55%): Earned Schedule with SPI is most accurate; watch CPI trend."}
    else:
        out["recommended"] = {"stage": "late", "recommended_eac": "cpi",
                              "guidance": "Late (≥55%): cost-efficiency forecasts firm up — EAC = BAC/CPI is dependable."}
    return out


def _budgeted_activities(db: Session, pid: str) -> list[dict[str, Any]]:
    """Activities carrying a budget, with parsed dates + % — the shared input for EV and PV curves."""
    out = []
    for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
        d = r.get("data") or {}
        budget = _n(d.get("budget"))
        if budget <= 0:
            continue
        frac, method = _measured_fraction(d)
        out.append({"budget": budget, "earned": frac, "method": method,
                    "start": _d(d.get("start")) or _d(d.get("actual_start")),
                    "finish": _d(d.get("finish")) or _d(d.get("actual_finish"))})
    return out


def _pv_at(acts: list[dict[str, Any]], when: date) -> float:
    """Cumulative Planned Value (BCWS) earned by `when` — Σ (linear planned fraction × budget)."""
    total = 0.0
    for a in acts:
        s, f = a["start"], a["finish"]
        if s and f and f > s:
            frac = max(0.0, min(1.0, (when - s).days / (f - s).days))
        elif f:
            frac = 1.0 if when >= f else 0.0
        else:
            frac = 0.0
        total += frac * a["budget"]
    return total


def earned_schedule(db: Session, pid: str, today: date, period: str = "week") -> dict[str, Any] | None:
    """**Earned Schedule** — the time-based extension that fixes classic SV/SPI decaying to $0/1.0 at
    project end. Projects current EV onto the time axis of the PV baseline curve:

        ES = C + (EV − PV_C) / (PV_{C+1} − PV_C)   (C = last period whose cumulative PV ≤ EV)
        SV(t) = ES − AT   ·   SPI(t) = ES / AT   ·   IEAC(t) = PD / SPI(t)  → forecast finish

    All in `period` units (week/month). Returns the PV curve too (reused by the S-curve)."""
    acts = _budgeted_activities(db, pid)
    dated = [a for a in acts if a["start"] and a["finish"]]
    if not dated:
        return None
    pstart = min(a["start"] for a in dated)
    pfinish = max(a["finish"] for a in dated)
    pdays = _PERIOD_DAYS.get(period, 7.0)
    ev = sum(a["earned"] * a["budget"] for a in acts)
    bac = sum(a["budget"] for a in acts)
    pd = max(1.0, (pfinish - pstart).days / pdays)                     # planned duration (periods)
    at = max(0.0, (today - pstart).days / pdays)                       # actual time elapsed (periods)

    # cumulative PV curve at each period boundary (0 … past the planned finish)
    curve = []
    for i in range(int(math.ceil(pd)) + 2):
        dt = pstart + timedelta(days=i * pdays)
        curve.append({"period": i, "date": dt.isoformat(), "pv": round(_pv_at(acts, dt), 2)})

    # ES: walk the curve to the point where EV would have been planned
    es = 0.0
    for i in range(len(curve) - 1):
        pv_c, pv_next = curve[i]["pv"], curve[i + 1]["pv"]
        if ev >= pv_next:
            es = i + 1
            continue
        if ev >= pv_c and pv_next > pv_c:
            es = i + (ev - pv_c) / (pv_next - pv_c)
        break
    es = min(es, pd)                                                    # cap at planned duration

    spi_t = round(es / at, 3) if at > 0 else None
    ieac_t = round(pd / spi_t, 2) if spi_t else None                   # forecast total duration (periods)
    forecast_finish = (pstart + timedelta(days=ieac_t * pdays)).isoformat() if ieac_t else None
    return {
        "period": period, "planned_start": pstart.isoformat(), "planned_finish": pfinish.isoformat(),
        "planned_duration_periods": round(pd, 2), "actual_time_periods": round(at, 2),
        "earned_schedule_periods": round(es, 2), "sv_t_periods": round(es - at, 2), "spi_t": spi_t,
        "spi_t_band": index_band(spi_t), "ieac_t_periods": ieac_t, "forecast_finish": forecast_finish,
        "days_late": round((ieac_t - pd) * pdays, 1) if ieac_t else None,
        "bac": round(bac, 2), "ev": round(ev, 2), "curve": curve,
        "note": "Earned Schedule stays meaningful at completion (unlike dollar SPI, which → 1.0 whether "
                "or not the job finished on time). SPI(t) < 1 = behind; forecast_finish from IEAC(t).",
    }


def _ev_fraction(a: dict[str, Any], when: date, today: date) -> float:
    """Reconstructed earned fraction of an activity at `when` — it earns linearly across its actual
    window (start→finish for completed work, start→today for work in progress to its current %)."""
    s = a["start"]
    if not s or when < s:
        return 0.0
    target = a["earned"]
    end = a["finish"] if a["earned"] >= 1.0 and a["finish"] else today
    if not end or end <= s:
        return target if when >= s else 0.0
    return target * max(0.0, min(1.0, (when - s).days / (end - s).days))


def scurve(db: Session, pid: str, today: date, period: str = "week") -> dict[str, Any] | None:
    """The classic EVM **S-curve**: cumulative **PV** (full planned baseline), **EV** and **AC** to the
    data date, over `period` buckets. EV/AC arrays stop at the data date (so their lines end there while
    PV runs to the planned finish) + BAC + the working EAC."""
    acts = _budgeted_activities(db, pid)
    dated = [a for a in acts if a["start"] and a["finish"]]
    if not dated:
        return None
    pstart = min(a["start"] for a in dated)
    pfinish = max(a["finish"] for a in dated)
    pdays = _PERIOD_DAYS.get(period, 7.0)
    bac = sum(a["budget"] for a in acts)

    # actual costs with a date, for the AC curve
    costs = []
    for r in me.list_records(db, "direct_cost", pid, limit=1_000_000):
        d = r.get("data") or {}
        costs.append((_d(d.get("date")) or today, _n(d.get("amount"))))

    n_plan = int(math.ceil((pfinish - pstart).days / pdays)) + 1
    at_periods = max(0, int(math.ceil((today - pstart).days / pdays)))
    labels, pv, ev, ac = [], [], [], []
    for i in range(n_plan + 1):
        dt = pstart + timedelta(days=i * pdays)
        labels.append(dt.isoformat())
        pv.append(round(_pv_at(acts, dt), 2))
        if i <= at_periods:                           # EV + AC only to the data date
            ev.append(round(sum(_ev_fraction(a, dt, today) * a["budget"] for a in acts), 2))
            ac.append(round(sum(amt for cd, amt in costs if cd <= dt), 2))
    cpi = round(ev[-1] / ac[-1], 3) if ac and ac[-1] else None
    spi = round(ev[-1] / pv[at_periods], 3) if ev and at_periods < len(pv) and pv[at_periods] else None
    return {"period": period, "labels": labels, "pv": pv, "ev": ev, "ac": ac,
            "bac": round(bac, 2), "eac": forecasts(bac, ev[-1] if ev else 0.0, ac[-1] if ac else 0.0,
                                                   cpi, spi)["eac_working"],
            "data_date_period": at_periods,
            "note": "PV is the full planned baseline; EV and AC run to the data date."}


def model_ev(db: Session, pid: str, data_date: str | None = None) -> dict[str, Any]:
    """**Model-based earned value** — EV grounded in *physically installed* model elements (field-
    verified GUIDs from the install-coverage engine), the units-complete method sourced from the model.
    It's independent of the billing/schedule %, so comparing it to the schedule EV catches over-reported
    or front-loaded-SOV progress. Needs a loaded property index + field verification.
    """
    from sqlalchemy import select

    from .models import ElementVerification
    from .routers.properties import _INDEX, _ensure_loaded

    _ensure_loaded(pid)
    total = len(_INDEX.get(pid, {}))
    rows = list(db.execute(select(ElementVerification.status, ElementVerification.guid)
                           .where(ElementVerification.project_id == pid)).all())
    installed = len({g for st, g in rows if st in ("installed", "verified")})
    tracked = len({g for _, g in rows})
    denom = total or tracked or 1
    model_pct = round(100 * installed / denom, 1)

    snap = snapshot(db, pid, data_date)
    bac = snap["totals"]["bac"]
    ev_sched = snap["totals"]["ev"]
    ev_model = round(bac * model_pct / 100, 2)
    divergence = round(ev_sched - ev_model, 2)                 # + = schedule ahead of physical install
    flag = bool(bac and divergence > 0.05 * bac)
    return {
        "total_elements": total, "installed_elements": installed, "model_percent_complete": model_pct,
        "bac": bac, "ev_model": ev_model, "ev_schedule": ev_sched, "divergence": divergence,
        "front_loaded_flag": flag,
        "note": "Model EV = installed % (field-verified elements) × BAC — the units-complete method from "
                "the model. If schedule EV exceeds model EV materially, reported progress is running "
                "ahead of physical installation (often a front-loaded SOV)."
                + ("" if total else " No property index loaded yet."),
    }


def snapshot(db: Session, pid: str, data_date: str | None = None) -> dict[str, Any]:
    """The full EVM snapshot at the data date: project totals (metrics + forecast family) + a
    per-control-account (cost code) breakdown + per-activity earned value."""
    today = _d(data_date) or date.today()

    # cost-code id -> label (code · name), for control-account rows
    cc_label: dict[str, str] = {}
    for r in me.list_records(db, "cost_code", pid, limit=1_000_000):
        d = r.get("data") or {}
        cc_label[r["id"]] = " · ".join(x for x in [d.get("code") or r.get("title"), d.get("description")] if x)

    # AC (ACWP) by cost code, from posted direct costs (job-cost actuals)
    ac_by_cc: dict[str, float] = {}
    ac_total = 0.0
    for r in me.list_records(db, "direct_cost", pid, limit=1_000_000):
        d = r.get("data") or {}
        amt = _n(d.get("amount"))
        ac_total += amt
        cc = d.get("cost_code")
        if cc:
            ac_by_cc[cc] = ac_by_cc.get(cc, 0.0) + amt

    # schedule earned value per activity, rolled up to control accounts
    ca: dict[str, dict[str, float]] = {}          # cost_code id -> {bac, ev, pv}
    unassigned = {"bac": 0.0, "ev": 0.0, "pv": 0.0}
    bac = ev = pv = 0.0
    activities: list[dict[str, Any]] = []
    for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
        d = r.get("data") or {}
        budget = _n(d.get("budget"))
        if budget <= 0:
            continue
        frac, method = _measured_fraction(d)
        planned = _planned_fraction(d, today)
        a_pv = planned * budget
        a_ev = a_pv if method == "loe" else frac * budget       # LOE earns exactly its planned value
        bac += budget; ev += a_ev; pv += a_pv
        cc = d.get("cost_code")
        bucket = ca.setdefault(cc, {"bac": 0.0, "ev": 0.0, "pv": 0.0}) if cc else unassigned
        bucket["bac"] += budget; bucket["ev"] += a_ev; bucket["pv"] += a_pv
        activities.append({"ref": r.get("ref"), "name": r.get("title") or d.get("name"),
                           "cost_code": cc_label.get(cc, "") if cc else "", "ev_method": method,
                           "budget": round(budget, 2), "percent": round(frac * 100, 1),
                           "ev": round(a_ev, 2), "pv": round(a_pv, 2), "sv": round(a_ev - a_pv, 2)})

    # control-account table: join schedule EV/PV/BAC with cost AC by cost code
    control_accounts = []
    seen = set(ca.keys())
    for cc in seen | set(ac_by_cc.keys()):
        b = ca.get(cc, {"bac": 0.0, "ev": 0.0, "pv": 0.0})
        a_ac = ac_by_cc.get(cc, 0.0)
        cpi = round(b["ev"] / a_ac, 3) if a_ac else None
        spi = round(b["ev"] / b["pv"], 3) if b["pv"] else None
        control_accounts.append({
            "cost_code": cc_label.get(cc, "(unassigned)"),
            "bac": round(b["bac"], 2), "pv": round(b["pv"], 2), "ev": round(b["ev"], 2), "ac": round(a_ac, 2),
            "cv": round(b["ev"] - a_ac, 2), "sv": round(b["ev"] - b["pv"], 2), "cpi": cpi, "spi": spi,
            "percent_complete": round(b["ev"] / b["bac"] * 100, 1) if b["bac"] else 0.0,
        })
    control_accounts.sort(key=lambda x: (x["cv"], x["sv"]))    # worst cost then schedule variance first

    cpi = round(ev / ac_total, 3) if ac_total else None
    spi = round(ev / pv, 3) if pv else None
    totals = {
        "data_date": today.isoformat(), "bac": round(bac, 2), "pv": round(pv, 2), "ev": round(ev, 2),
        "ac": round(ac_total, 2), "cv": round(ev - ac_total, 2), "sv": round(ev - pv, 2),
        "cpi": cpi, "spi": spi, "cpi_band": index_band(cpi), "spi_band": index_band(spi),
        "percent_complete": round(ev / bac * 100, 1) if bac else 0.0,
        "percent_spent": round(ac_total / bac * 100, 1) if bac else 0.0,
        "forecast": forecasts(bac, ev, ac_total, cpi, spi),
        "activity_count": len(activities),
        "note": "EV = schedule % × budget (control account = cost code). AC from posted direct costs. "
                "Forecasts are shown as a family; the best EAC is stage-dependent.",
    }
    return {"totals": totals, "control_accounts": control_accounts,
            "activities": sorted(activities, key=lambda x: x["sv"]),
            "earned_schedule": earned_schedule(db, pid, today)}
