"""RISK-BOARD — one register unifying the platform's **computed** risks.

The platform already computes risk in half a dozen places — Monte-Carlo schedule risk (P80 buffer +
delay drivers), predictive schedule alerts, EVM cost/schedule indices, the pre-flight issuance gate,
and open coordination issues — but each lives behind its own tool. This board pulls them into ONE
ranked register (severity → source → deep link), so a PM opens one panel and sees every signal the
engines have raised. Aggregation only: every item is re-derived from its engine on each call (no new
stored state), and every lane is fail-open — a broken source drops its lane, never the board.
"""
from __future__ import annotations

from datetime import date
from typing import Any

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def board(db, pid: str) -> dict[str, Any]:
    from . import modules as me

    items: list[dict[str, Any]] = []
    lanes: dict[str, str] = {}                      # lane -> ok | error (honest coverage report)

    def add(source: str, severity: str, title: str, detail: str, link: str | None = None,
            metric: float | None = None) -> None:
        items.append({"source": source, "severity": severity, "title": title,
                      "detail": detail, "link": link, "metric": metric})

    acts = []
    try:
        acts = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    except Exception:  # noqa: BLE001
        pass

    # 1) Monte-Carlo schedule risk — the P80 buffer + the top delay driver
    try:
        from . import schedule_risk
        if acts:
            sim = schedule_risk.simulate(acts, iterations=300, seed=7)
            det, buf = sim.get("deterministic_days"), sim.get("buffer_p80_days")
            if det and buf is not None and det > 0:
                ratio = buf / det
                sev = "high" if ratio >= 0.25 else "medium" if ratio >= 0.10 else "low"
                add("schedule-risk", sev, f"P80 completion needs a {buf}-day buffer",
                    f"Deterministic {det}d vs P80 {sim.get('p80_days')}d — a reliable commitment "
                    f"carries the buffer.", f"/projects/{pid}/schedule/risk", metric=buf)
                top = (sim.get("activities") or [None])[0]
                if top and top.get("criticality_pct", 0) >= 60:
                    add("schedule-risk", "medium",
                        f"{top.get('ref') or top.get('name')} drives the slip",
                        f"On the critical path in {top['criticality_pct']}% of simulations "
                        f"(mean slip {top.get('mean_slip_days', 0)}d) — protect or split it.",
                        f"/projects/{pid}/schedule/risk")
        lanes["schedule_risk"] = "ok"
    except Exception:  # noqa: BLE001
        lanes["schedule_risk"] = "error"

    # 2) Predictive schedule alerts (overdue / late starts / blocked predecessors / procurement)
    try:
        from . import px
        al = px.alerts(db, pid)
        for a in (al.get("alerts") or [])[:12]:
            add("schedule-alert", "high" if a.get("level") == "high" else "medium",
                f"{str(a.get('type', 'alert')).replace('_', ' ').title()}: {a.get('ref') or ''}".strip(),
                str(a.get("message") or a.get("detail") or ""), f"/projects/{pid}/schedule/alerts")
        lanes["schedule_alerts"] = "ok"
    except Exception:  # noqa: BLE001
        lanes["schedule_alerts"] = "error"

    # 3) EVM — cost/schedule performance indices below par
    try:
        from . import evm
        totals = (evm.snapshot(db, pid).get("totals") or {})
        for key, label in (("cpi", "Cost performance"), ("spi", "Schedule performance")):
            v = totals.get(key)
            if v is not None and v < 1.0:
                sev = "high" if v < 0.9 else "medium" if v < 0.97 else "low"
                add("evm", sev, f"{label} index {v}",
                    f"{key.upper()} {v} ({totals.get(key + '_band')}) — EAC family: "
                    f"{(totals.get('forecast') or {}).get('recommended', {}).get('recommended_eac', 'cpi')}.",
                    f"/projects/{pid}/schedule/evm", metric=v)
        lanes["evm"] = "ok"
    except Exception:  # noqa: BLE001
        lanes["evm"] = "error"

    # 4) Pre-flight issuance gate — every blocking check is a live risk to issuing
    try:
        from . import preflight
        gate = preflight.run(db, pid)
        for c in gate.get("checks", []):
            if c.get("status") == "fail":
                add("preflight", "high", f"Issuance blocker: {c.get('label')}",
                    str(c.get("detail") or ""), c.get("link") or f"/projects/{pid}/preflight")
        lanes["preflight"] = "ok"
    except Exception:  # noqa: BLE001
        lanes["preflight"] = "error"

    # 5) Coordination — overdue open topics (past their due date) age into risk
    try:
        from .models import Topic
        today = date.today().isoformat()
        overdue = [t for t in db.query(Topic).filter(Topic.project_id == pid, Topic.status != "closed")
                   if getattr(t, "due_date", None) and str(t.due_date)[:10] < today]
        if overdue:
            worst = sorted(overdue, key=lambda t: str(t.due_date))[0]
            add("coordination", "high" if len(overdue) >= 3 else "medium",
                f"{len(overdue)} overdue open issue(s)",
                f"Oldest: “{worst.title}” due {str(worst.due_date)[:10]} — aging coordination items "
                "become claims.", f"/projects/{pid}/topics", metric=float(len(overdue)))
        lanes["coordination"] = "ok"
    except Exception:  # noqa: BLE001
        lanes["coordination"] = "error"

    items.sort(key=lambda i: _SEV_ORDER.get(i["severity"], 3))
    by_sev = {s: sum(1 for i in items if i["severity"] == s) for s in ("high", "medium", "low")}
    return {
        "items": items, "count": len(items), "by_severity": by_sev, "lanes": lanes,
        "band": "critical" if by_sev["high"] >= 3 else "elevated" if by_sev["high"] else
                ("watch" if items else "clear"),
        "note": "Every row is re-derived from its engine (Monte-Carlo schedule risk · predictive "
                "alerts · EVM · pre-flight gate · overdue coordination) — one register, each item "
                "deep-linked to the tool that computed it.",
    }
