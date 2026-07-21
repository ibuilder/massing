"""MARGIN-CBS (R16) — one per-cost-code money picture tying the GC portal's separate cost modules
together: **budget** (the agreed number), **committed** (subcontracts/POs), **actual/direct** (costs
incurred), and **billed** (sub invoices), rolled up by cost code so a PM sees, per code, the projected
**buyout margin** (budget − committed), the **cost variance** (budget − actual), and the exposure flags
(over-committed / over-budget). Pure over the module records — the reconciliation the portal lacked.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def _num(v: Any) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def by_cost_code(db: Session, pid: str) -> dict[str, Any]:
    """Aggregate budget / committed / actual / billed by cost code → per-code margin + variance rows."""
    from . import modules as me
    from . import resolve_hint as rh

    codes = {r["id"]: (r.get("data") or {}) for r in me.list_records(db, "cost_code", pid, limit=100_000)}

    def label(ref: Any) -> str:
        d = codes.get(ref)
        if d:
            return (d.get("code") or "").strip() + ((" · " + d["description"]) if d.get("description") else "") or ref
        return str(ref) if ref else "(unassigned)"

    def code_of(ref: Any) -> str:
        """The bare cost-code string (e.g. ``03-3000``) — the filter a resolve-action jumps with."""
        return ((codes.get(ref) or {}).get("code") or "").strip()

    agg: dict[Any, dict] = {}

    def bucket(ref: Any) -> dict:
        return agg.setdefault(ref or "(unassigned)",
                              {"budget": 0.0, "committed": 0.0, "actual": 0.0, "billed": 0.0})

    # budget: prefer revised, else budget/original (the current control number)
    for r in me.list_records(db, "budget", pid, limit=100_000):
        d = r.get("data") or {}
        v = _num(d.get("revised")) or _num(d.get("budget")) or _num(d.get("original"))
        bucket(d.get("cost_code"))["budget"] += v
    for r in me.list_records(db, "commitment", pid, limit=100_000):
        d = r.get("data") or {}
        bucket(d.get("cost_code"))["committed"] += _num(d.get("amount"))
    for r in me.list_records(db, "direct_cost", pid, limit=100_000):
        d = r.get("data") or {}
        bucket(d.get("cost_code"))["actual"] += _num(d.get("amount"))
    for r in me.list_records(db, "sub_invoice", pid, limit=100_000):
        d = r.get("data") or {}
        bucket(d.get("cost_code"))["billed"] += _num(d.get("amount"))

    rows = []
    for ref, a in agg.items():
        budget, committed, actual, billed = a["budget"], a["committed"], a["actual"], a["billed"]
        buyout_margin = round(budget - committed, 2)      # projected margin from buying out below budget
        variance = round(budget - actual, 2)              # budget remaining vs actual incurred
        over_committed = committed > budget + 0.005
        over_budget = actual > budget + 0.005
        # UX-ACT: pair each exposure flag with a one-click action, filtered to this cost code — the PM
        # jumps straight to the records that caused it instead of hunting for them.
        code = code_of(ref)
        actions: list[dict] = []
        if over_budget:
            actions.append(rh.open_module("direct_cost", "Review direct costs", code or None))
        if over_committed:
            actions.append(rh.open_module("commitment", "Review commitments", code or None))
        rows.append({
            "cost_code": label(ref),
            "budget": round(budget, 2), "committed": round(committed, 2),
            "actual": round(actual, 2), "billed": round(billed, 2),
            "buyout_margin": buyout_margin, "variance": variance,
            "pct_committed": round(100.0 * committed / budget, 1) if budget else None,
            "pct_spent": round(100.0 * actual / budget, 1) if budget else None,
            "over_committed": over_committed,
            "over_budget": over_budget,
            "actions": actions,
        })
    rows.sort(key=lambda x: x["buyout_margin"])            # worst (thinnest / negative) margin first

    tb = sum(r["budget"] for r in rows)
    tc = sum(r["committed"] for r in rows)
    ta = sum(r["actual"] for r in rows)
    tbi = sum(r["billed"] for r in rows)
    return {
        "code_count": len(rows),
        "total_budget": round(tb, 2), "total_committed": round(tc, 2),
        "total_actual": round(ta, 2), "total_billed": round(tbi, 2),
        "total_buyout_margin": round(tb - tc, 2), "total_variance": round(tb - ta, 2),
        "pct_committed": round(100.0 * tc / tb, 1) if tb else None,
        "pct_spent": round(100.0 * ta / tb, 1) if tb else None,
        "over_committed_codes": sum(1 for r in rows if r["over_committed"]),
        "over_budget_codes": sum(1 for r in rows if r["over_budget"]),
        "rows": rows,
        "note": "Per-cost-code reconciliation: budget vs committed (subcontracts/POs) vs actual (direct "
                "costs) vs billed (sub invoices). Buyout margin = budget − committed (projected); variance "
                "= budget − actual (remaining). Over-committed / over-budget codes are flagged worst-first.",
    }
