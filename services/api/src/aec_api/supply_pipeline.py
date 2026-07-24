"""CRE-SUPPLY (R20) — **competitive supply weighted by recorded evidence, not by status label.**

"Under construction" on a broker deck and "under construction" with a recorded construction deed of
trust are not the same fact, and a rendering with no permit is neither certain supply nor zero. The
shipped absorption / lot-supply engines take a units number; this decides what that number should
be.

Two filters and a weight:

* **Window** — only projects delivering inside the subject's own delivery-and-lease-up window
  compete. A tower finishing three months after we stabilize is not our competition.
* **Product** — a project of a different product type is excluded, and *counted* as excluded, so a
  thin competitive set is visible rather than implied.
* **Evidence weight** — each project's units are discounted by what is actually *recorded* about
  it (a construction loan recorded > a permit issued > a planning application > a press release),
  not by the label someone attached. Rumored supply stays visibly separate from permitted supply
  in the output; it is never blended into a single count.

The result feeds `absorption.lot_supply_index` as an evidence-weighted VDL, with the raw and
weighted numbers both reported so the discount is auditable rather than hidden.
"""
from __future__ import annotations

from datetime import date
from typing import Any

# evidence key -> (label, weight, rank). Weight = the share of units counted as real supply.
EVIDENCE: dict[str, dict[str, Any]] = {
    "loan_recorded": {"label": "Construction loan recorded", "weight": 1.00, "rank": 1},
    "under_construction": {"label": "GC mobilized / vertical construction", "weight": 1.00, "rank": 2},
    "permit_issued": {"label": "Building permit issued", "weight": 0.85, "rank": 3},
    "permit_applied": {"label": "Permit application filed", "weight": 0.50, "rank": 4},
    "entitled": {"label": "Entitled / approved", "weight": 0.35, "rank": 5},
    "planning_filed": {"label": "Planning application filed", "weight": 0.20, "rank": 6},
    "announced": {"label": "Announced / rendering only", "weight": 0.05, "rank": 7},
    "unknown": {"label": "No recorded evidence", "weight": 0.05, "rank": 8},
}
RUMORED = ("announced", "unknown")     # never counted as certain supply


def _num(v: Any) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def evidence_of(project: dict) -> dict[str, Any]:
    """The strongest recorded evidence a project carries. Explicit flags win over a status label,
    because a label is an assertion and a recorded loan is a fact."""
    for key in sorted(EVIDENCE, key=lambda k: EVIDENCE[k]["rank"]):
        if key == "unknown":
            continue
        if project.get(key):
            return {"evidence": key, **EVIDENCE[key]}
    # fall back to a status string, mapped conservatively
    status = str(project.get("status") or "").lower().replace("-", " ")
    for key, spec in sorted(EVIDENCE.items(), key=lambda kv: kv[1]["rank"]):
        if key != "unknown" and key.replace("_", " ") in status:
            return {"evidence": key, **spec, "from_status_label": True}
    if "construction" in status:
        return {"evidence": "under_construction", **EVIDENCE["under_construction"],
                "from_status_label": True}
    if "permit" in status:
        return {"evidence": "permit_issued", **EVIDENCE["permit_issued"], "from_status_label": True}
    if any(w in status for w in ("propose", "rumor", "plan", "plann")):
        return {"evidence": "planning_filed", **EVIDENCE["planning_filed"], "from_status_label": True}
    return {"evidence": "unknown", **EVIDENCE["unknown"]}


def assess(projects: list[dict], *, window_start: Any = None, window_end: Any = None,
           product_type: str | None = None) -> dict[str, Any]:
    """Filter a supply pipeline to what actually competes, and weight it by recorded evidence.

    `projects` = [{name, units, delivery_date, product_type?, distance_mi?, status?,
                   loan_recorded?/permit_issued?/... booleans}]
    """
    ws, we = _parse(window_start), _parse(window_end)
    want = (product_type or "").strip().lower() or None

    competing, out_of_window, wrong_product = [], [], []
    for p in projects or []:
        ev = evidence_of(p)
        units = _num(p.get("units"))
        delivery = _parse(p.get("delivery_date"))
        row = {"name": p.get("name"), "units": units,
               "delivery_date": delivery.isoformat() if delivery else None,
               "product_type": p.get("product_type"), "distance_mi": p.get("distance_mi"),
               "evidence": ev["evidence"], "evidence_label": ev["label"],
               "weight": ev["weight"], "from_status_label": ev.get("from_status_label", False),
               "weighted_units": round(units * ev["weight"], 1),
               "rumored": ev["evidence"] in RUMORED}
        if want and str(p.get("product_type") or "").strip().lower() != want:
            wrong_product.append({**row, "excluded": "different product type"})
            continue
        if (ws or we) and delivery is None:
            out_of_window.append({**row, "excluded": "no delivery date to place in the window"})
            continue
        if ws and delivery and delivery < ws:
            out_of_window.append({**row, "excluded": "delivers before the window"})
            continue
        if we and delivery and delivery > we:
            out_of_window.append({**row, "excluded": "delivers after the window"})
            continue
        competing.append(row)

    competing.sort(key=lambda r: (-r["weighted_units"], r["name"] or ""))
    certain = [r for r in competing if not r["rumored"]]
    rumored = [r for r in competing if r["rumored"]]
    raw = sum(r["units"] for r in competing)
    weighted = sum(r["weighted_units"] for r in competing)
    by_evidence: dict[str, dict[str, Any]] = {}
    for r in competing:
        b = by_evidence.setdefault(r["evidence"], {"evidence": r["evidence"],
                                                   "label": r["evidence_label"],
                                                   "projects": 0, "units": 0.0, "weighted": 0.0})
        b["projects"] += 1
        b["units"] += r["units"]
        b["weighted"] = round(b["weighted"] + r["weighted_units"], 1)
    return {
        "window": {"start": ws.isoformat() if ws else None, "end": we.isoformat() if we else None},
        "product_type": want,
        "competing": competing,
        "certain_supply_units": round(sum(r["units"] for r in certain), 1),
        "rumored_supply_units": round(sum(r["units"] for r in rumored), 1),
        "raw_units": round(raw, 1), "weighted_units": round(weighted, 1),
        "discount_pct": round(100.0 * (1 - weighted / raw), 1) if raw else 0.0,
        "by_evidence": [by_evidence[k] for k in sorted(by_evidence,
                                                       key=lambda k: EVIDENCE[k]["rank"])],
        "excluded": {"out_of_window": out_of_window, "wrong_product": wrong_product,
                     "counts": {"out_of_window": len(out_of_window),
                                "wrong_product": len(wrong_product)}},
        "counts": {"competing": len(competing), "certain": len(certain), "rumored": len(rumored)},
        "note": ("Units are discounted by RECORDED evidence, not by status label; rumored supply is "
                 "reported separately and never blended into the certain count. Excluded projects "
                 "are listed with the reason so a thin competitive set is visible, not implied."),
    }


def supply_index(projects: list[dict], monthly_absorption: float, *,
                 window_start: Any = None, window_end: Any = None,
                 product_type: str | None = None,
                 equilibrium_months: float = 6.0) -> dict[str, Any]:
    """Evidence-weighted months-of-supply — the shipped Lot Supply Index over a VDL that has been
    filtered and discounted. Both the raw and weighted readings are returned, because the gap
    between them IS the argument."""
    from .absorption import lot_supply_index
    a = assess(projects, window_start=window_start, window_end=window_end, product_type=product_type)
    weighted = lot_supply_index(a["weighted_units"], monthly_absorption, equilibrium_months)
    raw = lot_supply_index(a["raw_units"], monthly_absorption, equilibrium_months)
    return {
        "supply": a,
        "weighted_index": weighted, "raw_index": raw,
        "delta_months": (round(raw["months_of_supply"] - weighted["months_of_supply"], 1)
                         if raw.get("months_of_supply") is not None
                         and weighted.get("months_of_supply") is not None else None),
        "note": ("The weighted index is the one to underwrite; the raw index is shown beside it so "
                 "the size of the evidence discount is visible rather than buried."),
    }
