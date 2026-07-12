"""Model → cost → GL traceability by **IFC GlobalId** — the thing no cost-code-only stack can do.

Every cost record (budget, commitment, direct cost, sub invoice) can carry `element_guids` — the IFC
GlobalIds of the building elements it pays for (the config engine stores them on the row). This walks
that link both ways:
  • `element_costs(guid)` — for one model element, every cost line that references it (what did this
    beam/slab actually cost?), grouped by kind and cost code.
  • `summary()` — cost **traceability coverage**: how much of the job's cost is tied to model elements
    vs. untraceable, overall and per cost code — the auditability story (billing/cost defensible against
    the model, not a spreadsheet).

Keyed on cost code, like everything else; degrades gracefully when no GUIDs are tagged yet.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

# cost-bearing modules → the field holding the dollar amount
COST_MODULES = {"budget": "revised", "commitment": "amount", "direct_cost": "amount", "sub_invoice": "amount"}


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _amount(kind: str, d: dict) -> float:
    if kind == "budget":
        return _n(d.get("revised") or d.get("budget"))
    return _n(d.get("amount"))


def _lines(db: Session, pid: str) -> list[dict]:
    """All cost lines with their amount, cost code, and referenced element GUIDs."""
    out: list[dict] = []
    for kind in COST_MODULES:
        if kind not in me.TABLES:
            continue
        for r in me.list_records(db, kind, pid, limit=100_000):
            d = r.get("data") or {}
            amt = _amount(kind, d)
            if amt == 0:
                continue
            out.append({"kind": kind, "ref": r.get("ref"), "cost_code": d.get("cost_code"),
                        "amount": round(amt, 2), "guids": list(r.get("element_guids") or [])})
    return out


def element_costs(db: Session, pid: str, guid: str) -> dict[str, Any]:
    """Every cost line that references this IFC element (by GlobalId)."""
    lines = [ln for ln in _lines(db, pid) if guid in ln["guids"]]
    by_kind: dict[str, float] = {}
    for ln in lines:
        by_kind[ln["kind"]] = round(by_kind.get(ln["kind"], 0.0) + ln["amount"], 2)
    return {"guid": guid, "lines": [{k: ln[k] for k in ("kind", "ref", "cost_code", "amount")} for ln in lines],
            "total": round(sum(ln["amount"] for ln in lines), 2), "by_kind": by_kind, "count": len(lines),
            "note": "Every budget / commitment / direct-cost / sub-invoice line tagged to this GlobalId."}


def element_records(db: Session, pid: str, guid: str) -> dict[str, Any]:
    """Reverse deep-link: every record across all pinnable modules that references this IFC element by
    GlobalId — the RFIs, coordination issues, change orders, field verifications, schedule activities,
    etc. tied to it. Closes the round-trip with the portal's "show in model" (record→element) direction:
    now selecting an element in the viewer surfaces the records that touch it."""
    groups: list[dict] = []
    total = 0
    for key in sorted(me.TABLES):
        mod = me.REGISTRY.get(key) or {}
        if not mod.get("pinnable"):                    # element tags live on pinnable modules
            continue
        hits = []
        for r in me.list_records(db, key, pid, limit=100_000):
            d = r.get("data") or {}
            if guid in (r.get("element_guids") or []) or d.get("guid") == guid:
                hits.append({"ref": r.get("ref"), "title": r.get("title") or "", "id": r.get("id"),
                             "state": r.get("workflow_state")})
        if hits:
            groups.append({"module": key, "module_name": mod.get("name", key), "icon": mod.get("icon", "📄"),
                           "count": len(hits), "records": hits[:50]})
            total += len(hits)
    groups.sort(key=lambda g: g["count"], reverse=True)
    return {"guid": guid, "total": total, "modules": groups,
            "note": "Records across pinnable modules tied to this GlobalId (by element_guids or data.guid)."}


def summary(db: Session, pid: str) -> dict[str, Any]:
    """Cost traceability coverage — traceable (tagged to model elements) vs untraceable, per cost code."""
    lines = _lines(db, pid)
    total = round(sum(ln["amount"] for ln in lines), 2)
    traceable = round(sum(ln["amount"] for ln in lines if ln["guids"]), 2)
    guids: set[str] = set()
    by_code: dict[str, dict[str, float]] = {}
    cc_label: dict[str, str] = {}
    for r in me.list_records(db, "cost_code", pid, limit=100_000) if "cost_code" in me.TABLES else []:
        d = r.get("data") or {}
        cc_label[r["id"]] = " · ".join(x for x in [d.get("code") or r.get("title"), d.get("description")] if x)
    for ln in lines:
        guids.update(ln["guids"])
        b = by_code.setdefault(ln["cost_code"] or "(unassigned)", {"total": 0.0, "traceable": 0.0})
        b["total"] += ln["amount"]
        if ln["guids"]:
            b["traceable"] += ln["amount"]
    by_cost_code = [{"cost_code": cc_label.get(k, k if k == "(unassigned)" else "(cost code)"),
                     "total": round(v["total"], 2), "traceable": round(v["traceable"], 2),
                     "coverage_pct": round(v["traceable"] / v["total"] * 100, 1) if v["total"] else 0.0}
                    for k, v in by_code.items()]
    by_cost_code.sort(key=lambda x: x["total"], reverse=True)
    return {"total_cost": total, "traceable_cost": traceable, "untraceable_cost": round(total - traceable, 2),
            "coverage_pct": round(traceable / total * 100, 1) if total else 0.0,
            "elements_referenced": len(guids), "line_count": len(lines),
            "by_cost_code": by_cost_code,
            "note": "Cost traceable to IFC elements by GlobalId. Tag cost records with the model elements "
                    "they pay for to raise coverage — then billing and cost are defensible against the model."}
