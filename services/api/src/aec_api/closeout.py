"""Closeout analytics — punchlist completion & ball-in-court, commissioning pass rate, completion
certificates, warranty expirations, and O&M-manual turnover. Pure read-side aggregation over the
punchlist / commissioning / completion_certificate / warranty / om_manual modules; no writes.
Mirrors the quality/safety register engines."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .timeutil import utc_today

PUNCH_DONE = ("verified",)
# punchlist workflow_state -> whose court the ball is in
PUNCH_COURT = {"open": "Responsible / Sub", "ready": "GC (verify)", "verified": "Verified"}
EXPIRING_WINDOW_DAYS = 90


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _d(r: dict) -> dict:
    return r.get("data") or r


def punch_rollup(punches: list[dict], as_of: date | None = None) -> dict[str, Any]:
    today = as_of or utc_today()
    by_state, by_trade, by_priority, ball_in_court = {}, {}, {}, {}
    overdue = verified = 0
    open_cost = 0.0
    rows = []
    for p in punches:
        d = _d(p)
        st = p.get("workflow_state") or "open"
        by_state[st] = by_state.get(st, 0) + 1
        court = PUNCH_COURT.get(st, st)
        ball_in_court[court] = ball_in_court.get(court, 0) + 1
        trade = (d.get("trade") or "(unassigned)").strip() or "(unassigned)"
        by_trade[trade] = by_trade.get(trade, 0) + 1
        pri = (d.get("priority") or "(none)").strip() or "(none)"
        by_priority[pri] = by_priority.get(pri, 0) + 1
        is_done = st in PUNCH_DONE
        if is_done:
            verified += 1
        else:
            open_cost += _num(d.get("cost"))
        due = _parse(d.get("due_date"))
        is_overdue = bool(due and due < today and not is_done)
        if is_overdue:
            overdue += 1
        rows.append({
            "ref": p.get("ref"), "description": d.get("description"), "state": st,
            "ball_in_court": court, "trade": trade, "priority": pri,
            "due_date": d.get("due_date"), "overdue": is_overdue, "cost": _num(d.get("cost")),
            "responsible": d.get("responsible"),
        })
    n = len(rows)
    return {
        "punch_count": n, "verified_count": verified, "open_count": n - verified,
        "overdue_count": overdue, "complete_pct": round(100 * verified / n, 1) if n else None,
        "open_cost": round(open_cost, 2),
        "ball_in_court": ball_in_court, "by_state": by_state,
        "by_trade": dict(sorted(by_trade.items())), "by_priority": dict(sorted(by_priority.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("trade") or "", r.get("ref") or "")),
    }


def commissioning_rollup(cx: list[dict]) -> dict[str, Any]:
    by_result, by_test_type, by_state = {}, {}, {}
    passed = failed = conditional = accepted = 0
    for c in cx:
        d = _d(c)
        st = c.get("workflow_state") or "open"
        by_state[st] = by_state.get(st, 0) + 1
        if st == "accepted":
            accepted += 1
        res = (d.get("result") or "(pending)").strip() or "(pending)"
        by_result[res] = by_result.get(res, 0) + 1
        if res == "Pass":
            passed += 1
        elif res == "Fail":
            failed += 1
        elif res == "Conditional":
            conditional += 1
        tt = (d.get("test_type") or "(unspecified)").strip() or "(unspecified)"
        by_test_type[tt] = by_test_type.get(tt, 0) + 1
    decided = passed + failed + conditional
    return {
        "cx_count": len(cx), "passed": passed, "failed": failed, "conditional": conditional,
        "accepted": accepted, "pass_rate": round(100 * passed / decided, 1) if decided else None,
        "by_result": dict(sorted(by_result.items())), "by_test_type": dict(sorted(by_test_type.items())),
        "by_state": by_state,
    }


def warranty_rollup(warranties: list[dict], as_of: date | None = None) -> dict[str, Any]:
    today = as_of or utc_today()
    horizon = today + timedelta(days=EXPIRING_WINDOW_DAYS)
    by_type = {}
    active = expired = expiring_soon = no_date = 0
    rows = []
    for w in warranties:
        d = _d(w)
        wt = (d.get("warranty_type") or "(untyped)").strip() or "(untyped)"
        by_type[wt] = by_type.get(wt, 0) + 1
        exp = _parse(d.get("expires"))
        if not exp:
            no_date += 1
            status = "(no expiry)"
        elif exp < today:
            expired += 1
            status = "expired"
        elif exp <= horizon:
            expiring_soon += 1
            status = "expiring"
        else:
            active += 1
            status = "active"
        rows.append({"ref": w.get("ref"), "name": d.get("name"), "vendor": d.get("vendor"),
                     "warranty_type": wt, "expires": d.get("expires"), "status": status})
    return {
        "warranty_count": len(warranties), "active": active, "expired": expired,
        "expiring_soon": expiring_soon, "no_expiry": no_date, "by_type": dict(sorted(by_type.items())),
        "rows": sorted(rows, key=lambda r: (r.get("expires") or "9999")),
    }


def om_rollup(manuals: list[dict]) -> dict[str, Any]:
    by_status = {}
    accepted = 0
    for m in manuals:
        d = _d(m)
        stt = (d.get("status") or "Pending").strip() or "Pending"
        by_status[stt] = by_status.get(stt, 0) + 1
        if stt == "Accepted":
            accepted += 1
    n = len(manuals)
    return {
        "om_count": n, "accepted": accepted,
        "accepted_pct": round(100 * accepted / n, 1) if n else None,
        "by_status": by_status,
    }


def certificates(certs: list[dict]) -> dict[str, Any]:
    by_type, by_state = {}, {}
    rows = []
    for c in certs:
        d = _d(c)
        ct = (d.get("type") or "(untyped)").strip() or "(untyped)"
        by_type[ct] = by_type.get(ct, 0) + 1
        st = c.get("workflow_state") or "draft"
        by_state[st] = by_state.get(st, 0) + 1
        rows.append({"ref": c.get("ref"), "subject": d.get("subject"), "type": ct,
                     "date": d.get("date"), "state": st})
    return {"cert_count": len(certs), "by_type": dict(sorted(by_type.items())),
            "by_state": by_state, "rows": rows}


def closeout_summary(db, pid: str) -> dict[str, Any]:
    from . import modules as me

    def _load(key):
        return me.list_records(db, key, pid, limit=100000) if key in me.TABLES else []

    return {
        "punchlist": punch_rollup(_load("punchlist")),
        "commissioning": commissioning_rollup(_load("commissioning")),
        "certificates": certificates(_load("completion_certificate")),
        "warranties": warranty_rollup(_load("warranty")),
        "om_manuals": om_rollup(_load("om_manual")),
    }
