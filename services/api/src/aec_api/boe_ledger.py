"""BOE-LEDGER (R17 Sprint C) — the **Basis-of-Estimate assumption ledger**: the traceability layer *under*
the numbers, pairing with EST-CONFIDENCE (which scores them).

Three deterministic reads over structured assumptions
(`{cost_code/ref, description, phase, qty, unit_cost, unit, source, quote_ref, escalation_pct,
contingency_pct, basis_date}` per line):

- **ledger(lines)** — normalize the BoE + a completeness read: which lines lack a source / basis date /
  quote ref — an undocumented basis is a dispute waiting to happen.
- **phase_diff(prev, curr)** — what changed between two estimate versions, per line: qty re-based, unit
  cost moved, escalation/contingency shifted, source upgraded (allowance → quote) — the assumption drift
  across SD → DD → CD.
- **vs_actuals(lines, actuals)** — once commitments/actuals land, the assumption→actual variance per line,
  **decomposed exactly** into the quantity effect ((aq−q)·uc) and the price effect (aq·(auc−uc)) — *which
  assumption* drove the miss, not just that it missed.
"""
from __future__ import annotations

from typing import Any

_DOC_FIELDS = ("source", "basis_date")     # every line should carry these; quote lines also a quote_ref


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _key(ln: dict) -> str:
    return str(ln.get("cost_code") or ln.get("ref") or ln.get("description") or "").strip().lower()


def _norm(ln: dict) -> dict[str, Any]:
    qty, uc = _num(ln.get("qty")), _num(ln.get("unit_cost"))
    return {
        "key": _key(ln), "cost_code": ln.get("cost_code"), "description": ln.get("description") or "",
        "phase": str(ln.get("phase") or "").upper() or None,
        "qty": qty or None, "unit": ln.get("unit"), "unit_cost": uc or None,
        "total": round(qty * uc, 2) if qty and uc else _num(ln.get("total")) or None,
        "source": str(ln.get("source") or "").lower() or None, "quote_ref": ln.get("quote_ref"),
        "escalation_pct": _num(ln.get("escalation_pct")) or None,
        "contingency_pct": _num(ln.get("contingency_pct")) or None,
        "basis_date": ln.get("basis_date"),
    }


def ledger(lines: list[dict]) -> dict[str, Any]:
    """The normalized BoE + documentation completeness (undocumented basis = dispute risk)."""
    rows = [_norm(ln) for ln in lines or [] if isinstance(ln, dict) and _key(ln)]
    issues = []
    for r in rows:
        missing = [f for f in _DOC_FIELDS if not r.get(f)]
        if r.get("source") == "quote" and not r.get("quote_ref"):
            missing.append("quote_ref")
        if missing:
            issues.append({"key": r["key"], "description": r["description"], "missing": missing})
    documented = len(rows) - len(issues)
    return {
        "line_count": len(rows), "documented": documented,
        "pct_documented": round(documented / len(rows), 3) if rows else 1.0,
        "undocumented": issues, "lines": rows,
        "note": "Basis-of-Estimate ledger: every line's assumptions (source · quote ref · escalation · "
                "contingency · basis date), with the undocumented-basis lines surfaced — an estimate you "
                "can defend line-by-line.",
    }


_TRACKED = ("qty", "unit_cost", "escalation_pct", "contingency_pct", "source", "quote_ref")


def phase_diff(prev: list[dict], curr: list[dict]) -> dict[str, Any]:
    """Assumption drift between two estimate versions (SD→DD→CD), per line + added/removed."""
    p = {r["key"]: r for r in (_norm(x) for x in prev or []) if r["key"]}
    c = {r["key"]: r for r in (_norm(x) for x in curr or []) if r["key"]}
    changed = []
    for k in sorted(p.keys() & c.keys()):
        deltas = []
        for f in _TRACKED:
            a, b = p[k].get(f), c[k].get(f)
            if a != b and not (a is None and b is None):
                deltas.append({"field": f, "from": a, "to": b})
        if deltas:
            changed.append({"key": k, "description": c[k]["description"] or p[k]["description"],
                            "changes": deltas,
                            "total_from": p[k]["total"], "total_to": c[k]["total"],
                            "total_delta": round((c[k]["total"] or 0) - (p[k]["total"] or 0), 2)})
    return {
        "compared": len(p.keys() & c.keys()), "changed": len(changed),
        "added": sorted(c.keys() - p.keys()), "removed": sorted(p.keys() - c.keys()),
        "changes": sorted(changed, key=lambda r: -abs(r["total_delta"] or 0)),
        "note": "Assumption drift between estimate versions: per-line field changes (qty re-based · unit "
                "cost moved · escalation/contingency shifted · source upgraded) with the total impact, "
                "biggest movement first.",
    }


def vs_actuals(lines: list[dict], actuals: list[dict]) -> dict[str, Any]:
    """Assumption→actual variance, decomposed exactly: qty effect (Δq·uc) + price effect (aq·Δuc)."""
    a_by: dict[str, dict] = {}
    for a in actuals or []:
        k = _key(a)
        if k:
            g = a_by.setdefault(k, {"qty": 0.0, "cost": 0.0})
            g["qty"] += _num(a.get("qty") or a.get("actual_qty"))
            g["cost"] += _num(a.get("cost") or a.get("actual_cost"))
    rows = []
    tot_var = tot_qty_eff = tot_price_eff = 0.0
    for ln in (_norm(x) for x in lines or []):
        if not ln["key"] or ln["key"] not in a_by:
            continue
        act = a_by[ln["key"]]
        q, uc = ln["qty"] or 0.0, ln["unit_cost"] or 0.0
        aq = act["qty"] or 0.0
        auc = (act["cost"] / aq) if aq else 0.0
        assumed_total = q * uc
        variance = round(act["cost"] - assumed_total, 2)
        qty_eff = round((aq - q) * uc, 2)
        price_eff = round(aq * (auc - uc), 2)
        driver = "quantity" if abs(qty_eff) >= abs(price_eff) else "price"
        rows.append({"key": ln["key"], "description": ln["description"],
                     "assumed_qty": q or None, "actual_qty": aq or None,
                     "assumed_unit_cost": uc or None, "actual_unit_cost": round(auc, 2) or None,
                     "assumed_total": round(assumed_total, 2), "actual_total": round(act["cost"], 2),
                     "variance": variance, "qty_effect": qty_eff, "price_effect": price_eff,
                     "driver": driver, "source": ln["source"], "quote_ref": ln["quote_ref"]})
        tot_var += variance
        tot_qty_eff += qty_eff
        tot_price_eff += price_eff
    rows.sort(key=lambda r: -abs(r["variance"]))
    return {
        "matched": len(rows), "total_variance": round(tot_var, 2),
        "qty_effect": round(tot_qty_eff, 2), "price_effect": round(tot_price_eff, 2),
        "rows": rows,
        "note": "Assumption→actual variance decomposed exactly (qty effect = Δqty × assumed unit cost; "
                "price effect = actual qty × Δunit cost; they sum to the variance) — WHICH assumption "
                "drove the miss, worst first.",
    }
