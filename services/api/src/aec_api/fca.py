"""Facility Condition Assessment (FCA) + Facility Condition Index (FCI) — the operations-phase
condition engine.

An FCA inventories every building element (classified by UNIFORMAT II — ASTM E1557), rates its
condition, and prices the work needed to correct its deficiencies. The headline metric is the
**Facility Condition Index**:

    FCI = (deferred maintenance + capital renewal due) / current replacement value (CRV)

Lower is better. Industry bands: Good < 5%, Fair 5-10%, Poor 10-30%, Critical > 30%. Deferred
maintenance is the sum of open deficiency costs; capital renewal is the replacement value of elements
whose remaining useful life has run out. FCI recomputes as elements are resolved (they leave the
backlog), and rolls up to a **portfolio** view so capital is prioritized to the worst-off buildings.
This engine reads the config-driven `fca_element` records and feeds the reserve/CIP forecast
(`reserve.study`) with condition-based costs alongside the age-based ones."""
from __future__ import annotations

from datetime import date
from typing import Any

from . import modules as me
from .models import Project

# FCI bands (fraction of CRV). Lower = healthier building.
_BANDS = ((0.05, "Good"), (0.10, "Fair"), (0.30, "Poor"), (float("inf"), "Critical"))
_DEFAULT_CRV_PSF = 350.0   # fallback current-replacement-value $/sf when elements carry no cost


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _year(v) -> int | None:
    try:
        return int(str(v)[:4]) if v else None
    except ValueError:
        return None


def _rating(v) -> int | None:
    """Condition select stores '1 - Excellent' etc — pull the leading integer."""
    try:
        return int(str(v).strip()[0])
    except (ValueError, IndexError):
        return None


def band(fci_fraction: float) -> str:
    for hi, name in _BANDS:
        if fci_fraction <= hi:
            return name
    return "Critical"


def _renewal_due(d: dict, this_year: int) -> bool:
    """True when an element has reached the end of its useful life (capital renewal owed)."""
    life = int(float(d.get("expected_life_years") or 0) or 0)
    inst = _year(d.get("install_date"))
    if life <= 0 or inst is None:
        return False
    return (inst + life) <= this_year


def index(db, pid: str, crv: float | None = None, gfa_sf: float | None = None) -> dict[str, Any]:
    """The FCI dashboard for one project: the index + band, the deferred/renewal split, and the
    breakdowns (by UNIFORMAT group, by condition rating, worst elements, recommended-year forecast)."""
    this_year = date.today().year
    rows = me.list_records(db, "fca_element", pid, limit=100000)

    deferred = renewal = crv_sum = 0.0
    by_uni: dict[str, dict] = {}
    by_cond: dict[int, int] = {}
    worst: list[dict] = []
    by_year: dict[int, float] = {}
    open_count = 0

    for r in rows:
        d = _d(r)
        state = r.get("workflow_state") or "identified"
        rep = float(d.get("replacement_cost") or 0)
        crv_sum += rep
        rating = _rating(d.get("condition_rating"))
        if rating:
            by_cond[rating] = by_cond.get(rating, 0) + 1
        uni = d.get("uniformat") or "(unclassified)"
        u = by_uni.setdefault(uni, {"group": uni, "count": 0, "deferred": 0.0, "renewal": 0.0, "crv": 0.0})
        u["count"] += 1
        u["crv"] += rep

        if state == "resolved":                        # left the backlog
            continue
        open_count += 1
        deff = float(d.get("deficiency_cost") or 0)
        ren = rep if _renewal_due(d, this_year) else 0.0
        deferred += deff
        renewal += ren
        u["deferred"] += deff
        u["renewal"] += ren
        item_cost = deff + ren
        if item_cost > 0:
            worst.append({"ref": r.get("ref"), "element": d.get("element") or r.get("ref"),
                          "uniformat": uni, "condition": d.get("condition_rating") or "",
                          "cost": round(item_cost, 0)})
            yr = _year(d.get("recommended_year")) or this_year
            by_year[yr] = by_year.get(yr, 0.0) + item_cost

    crv_total = float(crv) if crv else (crv_sum or (float(gfa_sf) * _DEFAULT_CRV_PSF if gfa_sf else 0.0))
    numerator = deferred + renewal
    fci_frac = (numerator / crv_total) if crv_total > 0 else 0.0

    for u in by_uni.values():
        u["deferred"] = round(u["deferred"], 0)
        u["renewal"] = round(u["renewal"], 0)
        u["crv"] = round(u["crv"], 0)
        u["fci_pct"] = round(100 * (u["deferred"] + u["renewal"]) / u["crv"], 1) if u["crv"] > 0 else None

    return {
        "elements": len(rows), "open_deficiencies": open_count,
        "crv": round(crv_total, 0), "crv_source": "provided" if crv else ("elements" if crv_sum else "gfa_estimate"),
        "deferred_maintenance": round(deferred, 0), "capital_renewal": round(renewal, 0),
        "fci_pct": round(100 * fci_frac, 1), "band": band(fci_frac),
        "by_uniformat": sorted(by_uni.values(), key=lambda x: -(x["deferred"] + x["renewal"])),
        "by_condition": {str(k): by_cond[k] for k in sorted(by_cond)},
        "worst_elements": sorted(worst, key=lambda x: -x["cost"])[:15],
        "recommended_by_year": [{"year": y, "cost": round(by_year[y], 0)} for y in sorted(by_year)],
        "bands": {"good": "< 5%", "fair": "5-10%", "poor": "10-30%", "critical": "> 30%"},
        "note": "FCI = (deferred maintenance + capital renewal due) / current replacement value. "
                "Deferred = open deficiency costs; renewal = replacement value of elements past their "
                "useful life. Resolved elements leave the backlog. Lower FCI = healthier facility.",
    }


def portfolio(db) -> dict[str, Any]:
    """Per-project FCI across the portfolio, worst-first — the capital-prioritization view (allocate
    to the highest-FCI buildings, which carry the largest backlog relative to value)."""
    import logging
    out = []
    for p in db.query(Project).all():
        try:
            idx = index(db, p.id)
        except Exception:                              # noqa: BLE001,S112 — a bad project shouldn't sink the roll-up
            logging.getLogger(__name__).exception("fca.portfolio: skipped project %s", p.id)
            continue  # nosec B112 — logged above; one malformed project must not break the portfolio view
        if not idx["elements"]:
            continue
        out.append({"project_id": p.id, "project": p.name or p.id, "fci_pct": idx["fci_pct"],
                    "band": idx["band"], "crv": idx["crv"],
                    "backlog": round(idx["deferred_maintenance"] + idx["capital_renewal"], 0),
                    "open_deficiencies": idx["open_deficiencies"]})
    out.sort(key=lambda x: -x["fci_pct"])
    return {"projects": out, "count": len(out),
            "note": "Facility Condition Index per project, worst-first. The highest-FCI buildings carry "
                    "the largest deferred backlog relative to their replacement value — fund those first."}


def reserve_events(db, pid: str, this_year: int, end_year: int) -> list[dict]:
    """Condition-based events for the reserve/CIP schedule: each open FCA deficiency lands in its
    recommended year (default: now) so the funding forecast reflects real condition, not just age.
    Reused by `reserve.study`."""
    events = []
    for r in me.list_records(db, "fca_element", pid, limit=100000):
        if r.get("workflow_state") == "resolved":
            continue
        d = _d(r)
        cost = float(d.get("deficiency_cost") or 0)
        if cost <= 0:
            continue
        yr = _year(d.get("recommended_year")) or this_year
        yr = max(this_year, min(yr, end_year))
        events.append({"year": yr, "item": d.get("element") or r.get("ref"), "cost": cost,
                       "source": "fca", "ref": r.get("ref")})
    return events
