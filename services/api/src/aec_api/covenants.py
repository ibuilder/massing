"""CRE-COVENANT (R20) — **the loan covenant and reporting-obligation register.**

Timing alone can breach a loan. A borrower with clean financials who files on day nine of a
"ten business days" notice — counted from the lender's notice date, not from the day it landed —
has breached exactly as surely as one who missed a DSCR test. The two fields that cause that are
almost never modelled anywhere:

* **`day_basis`** — calendar days or *business* days (and, for business days, which holidays).
* **`clock_start`** — does the clock start at the lender's notice date, or at our receipt of it?

So they are first-class here, required, and the calculated due date shows its work: the anchor
date, the basis, the count, and every non-working day it skipped. A due date a reviewer cannot
re-derive by hand is not a due date.

Financial covenants (DSCR, debt yield, LTV, liquidity) carry their test, threshold, direction,
frequency and cure right; `test_covenants` evaluates supplied actuals against them and reports
pass / breach / **cure-period-open** separately, because a breach inside an open cure window is a
different conversation from one outside it.

Everything is deterministic date arithmetic and comparison — no parsing of the loan document
itself, which stays a human/counsel job. The register is what the reading produces.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

DAY_BASES = ("calendar", "business")
CLOCK_STARTS = ("lender_notice", "our_receipt")
DIRECTIONS = ("min", "max")           # min: actual must be >= threshold. max: actual must be <=

_WEEKEND = (5, 6)                     # Saturday, Sunday


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def add_days(anchor: date, count: int, basis: str = "calendar",
             holidays: list | None = None) -> dict[str, Any]:
    """Advance `count` days from `anchor` on the given basis, showing the work.

    Business-day counting skips weekends and the supplied holiday list; the anchor day itself is
    day zero (the standard "within N days of X" reading). Returns the due date plus every skipped
    day, so the number can be checked by hand.
    """
    basis = basis if basis in DAY_BASES else "calendar"
    hol = {d for d in (_parse(h) for h in (holidays or [])) if d}
    if basis == "calendar":
        return {"due": anchor + timedelta(days=int(count)), "basis": basis,
                "count": int(count), "anchor": anchor, "skipped": []}
    cur, moved, skipped = anchor, 0, []
    while moved < int(count):
        cur += timedelta(days=1)
        if cur.weekday() in _WEEKEND:
            skipped.append({"date": cur.isoformat(), "why": "weekend"})
            continue
        if cur in hol:
            skipped.append({"date": cur.isoformat(), "why": "holiday"})
            continue
        moved += 1
    return {"due": cur, "basis": basis, "count": int(count), "anchor": anchor, "skipped": skipped}


def obligation_due(ob: dict, holidays: list | None = None) -> dict[str, Any]:
    """The due date for one reporting obligation, with the clock-start choice made explicit.

    `ob` = {name, days, day_basis, clock_start, lender_notice_date?, received_date?,
            period_end?, delivered_date?}
    """
    basis = str(ob.get("day_basis") or "calendar").lower()
    clock = str(ob.get("clock_start") or "lender_notice").lower()
    if clock not in CLOCK_STARTS:
        clock = "lender_notice"
    notice = _parse(ob.get("lender_notice_date"))
    received = _parse(ob.get("received_date"))
    period_end = _parse(ob.get("period_end"))
    anchor = (received if clock == "our_receipt" else notice) or period_end
    if anchor is None:
        return {"name": ob.get("name"), "computable": False,
                "reason": ("needs an anchor date — lender_notice_date / received_date for a "
                           "notice-triggered item, or period_end for a periodic one"),
                "day_basis": basis, "clock_start": clock}
    days = int(_num(ob.get("days")) or 0)
    calc = add_days(anchor, days, basis, holidays)
    delivered = _parse(ob.get("delivered_date"))
    out = {
        "name": ob.get("name"), "computable": True, "days": days, "day_basis": basis,
        "clock_start": clock, "anchor_date": anchor.isoformat(),
        "anchor_source": ("our receipt" if clock == "our_receipt" and received
                          else "lender notice" if notice and clock == "lender_notice"
                          else "period end"),
        "due_date": calc["due"].isoformat(), "non_working_days_skipped": calc["skipped"],
        "delivered_date": delivered.isoformat() if delivered else None,
    }
    if delivered:
        out["status"] = "filed_on_time" if delivered <= calc["due"] else "filed_late"
        out["days_early"] = (calc["due"] - delivered).days
    else:
        out["status"] = "outstanding"
    # a notice-triggered item where the two clock readings disagree is the classic trap — say so
    if notice and received and notice != received:
        alt_anchor = notice if clock == "our_receipt" else received
        alt = add_days(alt_anchor, days, basis, holidays)
        out["clock_start_matters"] = True
        out["alternate_reading"] = {
            "clock_start": "lender_notice" if clock == "our_receipt" else "our_receipt",
            "due_date": alt["due"].isoformat(),
            "days_difference": (calc["due"] - alt["due"]).days,
            "warning": ("The two clock-start readings give different due dates — confirm the "
                        "counting basis with counsel before the calendar goes live."),
        }
    return out


def calendar(obligations: list[dict], as_of: date | None = None,
             holidays: list | None = None, horizon_days: int = 90) -> dict[str, Any]:
    """The forward calendar: what is due, what is overdue, what is at risk inside the horizon."""
    today = as_of or date.today()
    rows = [obligation_due(o, holidays) for o in (obligations or [])]
    computable = [r for r in rows if r.get("computable")]
    for r in computable:
        due = _parse(r["due_date"])
        r["days_remaining"] = (due - today).days if due else None
        if r["status"] == "outstanding":
            if r["days_remaining"] is not None and r["days_remaining"] < 0:
                r["risk"] = "overdue"
            elif r["days_remaining"] is not None and r["days_remaining"] <= 14:
                r["risk"] = "due_soon"
            else:
                r["risk"] = "ok"
        else:
            r["risk"] = "late_filed" if r["status"] == "filed_late" else "ok"
    upcoming = sorted((r for r in computable
                       if r["status"] == "outstanding"
                       and r.get("days_remaining") is not None
                       and r["days_remaining"] <= horizon_days),
                      key=lambda r: r["days_remaining"])
    return {
        "as_of": today.isoformat(), "horizon_days": horizon_days,
        "obligations": rows,
        "not_computable": [{"name": r.get("name"), "reason": r.get("reason")}
                           for r in rows if not r.get("computable")],
        "upcoming": upcoming,
        "overdue": [r for r in computable if r.get("risk") == "overdue"],
        "counts": {"total": len(rows), "computable": len(computable),
                   "outstanding": sum(1 for r in computable if r["status"] == "outstanding"),
                   "overdue": sum(1 for r in computable if r.get("risk") == "overdue"),
                   "due_soon": sum(1 for r in computable if r.get("risk") == "due_soon"),
                   "filed_late": sum(1 for r in computable if r["status"] == "filed_late")},
        "note": ("Due dates show their anchor, basis and skipped non-working days so a reviewer can "
                 "re-derive them by hand. Items whose two clock-start readings disagree are flagged."),
    }


def test_covenants(covenants: list[dict], actuals: dict | None = None,
                   as_of: date | None = None) -> dict[str, Any]:
    """Evaluate financial covenants against supplied actuals.

    `covenants` = [{name, metric, direction: min|max, threshold, frequency?, cure_days?,
                    breach_date?}]. A covenant whose metric is absent from `actuals` is reported
    **untested** with what it needed — never as a pass.
    """
    today = as_of or date.today()
    actuals = actuals or {}
    rows: list[dict[str, Any]] = []
    for c in covenants or []:
        metric = str(c.get("metric") or c.get("name") or "").strip()
        threshold = _num(c.get("threshold"))
        direction = str(c.get("direction") or "min").lower()
        direction = direction if direction in DIRECTIONS else "min"
        actual = _num(actuals.get(metric))
        base = {"name": c.get("name") or metric, "metric": metric, "direction": direction,
                "threshold": threshold, "frequency": c.get("frequency")}
        if actual is None or threshold is None:
            rows.append({**base, "tested": False, "actual": actual,
                         "reason": (f"no actual supplied for '{metric}'" if actual is None
                                    else "covenant has no threshold")})
            continue
        passing = actual >= threshold if direction == "min" else actual <= threshold
        row = {**base, "tested": True, "actual": actual, "passing": passing,
               "headroom": round((actual - threshold) if direction == "min"
                                 else (threshold - actual), 4)}
        if not passing:
            cure_days = int(_num(c.get("cure_days")) or 0)
            breach = _parse(c.get("breach_date")) or today
            cure_end = breach + timedelta(days=cure_days) if cure_days else None
            row["status"] = ("cure_period_open" if cure_end and today <= cure_end else "breach")
            row["cure_days"] = cure_days or None
            row["cure_ends"] = cure_end.isoformat() if cure_end else None
            row["note"] = ("A breach inside an open cure window is a different conversation from "
                           "one outside it — this one is "
                           + ("still curable." if row["status"] == "cure_period_open"
                              else "past its cure period." if cure_end else "uncured (no cure right)."))
        else:
            row["status"] = "pass"
        rows.append(row)
    tested = [r for r in rows if r["tested"]]
    return {
        "as_of": today.isoformat(), "covenants": rows,
        "untested": [{"name": r["name"], "reason": r["reason"]} for r in rows if not r["tested"]],
        "counts": {"total": len(rows), "tested": len(tested),
                   "untested": len(rows) - len(tested),
                   "passing": sum(1 for r in tested if r["passing"]),
                   "breach": sum(1 for r in tested if r.get("status") == "breach"),
                   "cure_period_open": sum(1 for r in tested if r.get("status") == "cure_period_open")},
        "clean": bool(tested) and all(r["passing"] for r in tested),
        "note": ("A covenant with no supplied actual is reported UNTESTED with what it needed — "
                 "an untested covenant is not a passing one."),
    }


def register(loan: dict, actuals: dict | None = None, as_of: date | None = None) -> dict[str, Any]:
    """The whole register for one loan: reporting calendar + covenant tests + one verdict."""
    holidays = loan.get("holidays") or []
    cal = calendar(loan.get("obligations") or [], as_of, holidays,
                   int(_num(loan.get("horizon_days")) or 90))
    cov = test_covenants(loan.get("covenants") or [], actuals, as_of)
    return {
        "loan": {"name": loan.get("name"), "lender": loan.get("lender")},
        "reporting": cal, "financial": cov,
        "at_risk": (cal["counts"]["overdue"] > 0 or cal["counts"]["due_soon"] > 0
                    or cov["counts"]["breach"] > 0 or cov["counts"]["cure_period_open"] > 0),
        "summary": {
            "overdue_filings": cal["counts"]["overdue"],
            "filings_due_soon": cal["counts"]["due_soon"],
            "covenant_breaches": cov["counts"]["breach"],
            "in_cure_period": cov["counts"]["cure_period_open"],
            "untested_covenants": cov["counts"]["untested"],
            "uncomputable_obligations": len(cal["not_computable"]),
        },
    }
