"""Design-lifecycle endpoints — the RIBA/AIA phase spine + itemized soft costs for a project."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import adjacency, design_phase, resilience, soft_costs, spine
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/projects/{pid}/program/summary")
def program_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Concept space-program rollup + adjacency graph: total/net/gross area, mix by use, the node/edge
    graph, unmet adjacency preferences, and the massing hints (gross area + use mix) it feeds."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return adjacency.summary(db, pid)


def _hard_cost(p: Project) -> float:
    """Project hard cost from the seeded dev budget (category='hard'); 0 if not seeded yet."""
    budget = getattr(p, "dev_budget", None) or {}
    total = 0.0
    for ln in budget.get("lines", []):
        if (ln.get("category") or "").lower() == "hard":
            total += float(ln.get("unit_cost") or 0) * float(ln.get("quantity") or 1)
    return total


@router.get("/projects/{pid}/lifecycle")
def lifecycle(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """The project's design phases (RIBA 0–7 ↔ AIA) with gate state, deliverables, ISO-19650 status,
    and the phase-allocated A/E design fee from the itemized soft costs."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    hard = _hard_cost(p)
    lc = design_phase.lifecycle(db, pid, hard_cost=hard, soft_cost_pct=25.0)
    lc["soft_costs"] = soft_costs.itemize(hard, 25.0) if hard else None
    lc["hard_cost"] = hard
    return lc


@router.post("/projects/{pid}/lifecycle/seed")
def seed(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Seed the eight design-phase records on a project (idempotent)."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return design_phase.seed_phases(db, pid, actor)


@router.get("/lifecycle/reference")
def reference(_: str = Depends(current_user)):
    """The canonical RIBA↔AIA phase definitions + soft-cost taxonomy (for the UI, no project needed)."""
    return {"phases": design_phase.PHASES,
            "soft_cost_components": soft_costs.COMPONENTS,
            "ae_phase_split": soft_costs.AE_PHASE_SPLIT}


@router.get("/projects/{pid}/resilience/flood")
def resilience_flood(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Flood risk (ASCE 24 / FEMA): the Design Flood Elevation (BFE + freeboard) and the flood-proof-MEP
    check — asset-register items installed below the DFE, flagged to be elevated or flood-proofed."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.flood_assessment(db, pid)


@router.get("/projects/{pid}/resilience/stormwater")
def resilience_stormwater(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Stormwater (Rational Method): peak runoff Q = C·i·A per catchment plus a first-order detention
    volume, so drainage is sized against a real design storm."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.stormwater(db, pid)


@router.get("/projects/{pid}/resilience/weather")
def resilience_weather(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Weather-sequenced construction: weather-sensitive schedule activities, the site-weather-risk
    register, and weather-delay days rolled up from the daily reports."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.weather(db, pid)


@router.get("/projects/{pid}/resilience/climate-risk")
def resilience_climate_risk(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Physical climate-risk rollup for ESG — flood exposure + stormwater load + site-weather hazards +
    logged weather delays folded into a single scored rating with the driving factors."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.climate_risk(db, pid)


@router.get("/projects/{pid}/spine/traceability")
def spine_traceability(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Discipline Spine traceability — trace discipline → sheets → specs → bid packages → cost codes →
    budget, with per-discipline rollups and the coverage gaps (unpackaged specs, unbudgeted packages,
    un-specced sheets) so scope can't fall between the model, the documents and the money."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return spine.traceability(db, pid)


@router.get("/projects/{pid}/diligence/readiness")
def diligence_readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(current_user)):
    """Pre-acquisition go/no-go rollup: due-diligence items by category/state (cleared vs flagged vs
    open, high-risk flags) + entitlement applications by status (approved vs pending vs denied,
    approvals nearing expiration). The screen a developer reads before releasing contingencies."""
    from datetime import date, timedelta

    from .. import modules as me
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")

    dd = me.list_records(db, "due_diligence", pid, limit=1000) if "due_diligence" in me.TABLES else []
    by_cat: dict[str, dict] = {}
    high_risk = []
    for r in dd:
        d = r.get("data") or {}
        cat = d.get("category") or "Other"
        c = by_cat.setdefault(cat, {"total": 0, "cleared": 0, "flagged": 0, "open": 0})
        c["total"] += 1
        st = r.get("workflow_state")
        c["cleared" if st == "cleared" else "flagged" if st == "flagged" else "open"] += 1
        if (d.get("risk") or "") in ("High", "Deal-breaker"):
            high_risk.append({"ref": r.get("ref"), "item": r.get("title"), "risk": d["risk"],
                              "category": cat, "state": st})

    ents = me.list_records(db, "entitlement", pid, limit=1000) if "entitlement" in me.TABLES else []
    ent_counts: dict[str, int] = {}
    expiring = []
    horizon = date.today() + timedelta(days=180)
    for r in ents:
        st = r.get("workflow_state") or "draft"
        ent_counts[st] = ent_counts.get(st, 0) + 1
        exp = (r.get("data") or {}).get("approval_expires")
        if st == "approved" and exp:
            try:
                if date.fromisoformat(str(exp)[:10]) <= horizon:
                    expiring.append({"ref": r.get("ref"), "application": r.get("title"), "expires": exp})
            except ValueError:
                pass

    dd_total = len(dd)
    dd_cleared = sum(c["cleared"] for c in by_cat.values())
    ents_pending = sum(v for k, v in ent_counts.items() if k in ("draft", "submitted", "hearing", "appealed"))
    return {
        "due_diligence": {"total": dd_total, "cleared": dd_cleared,
                          "flagged": sum(c["flagged"] for c in by_cat.values()),
                          "by_category": by_cat, "high_risk": high_risk},
        "entitlements": {"total": len(ents), "by_state": ent_counts,
                         "approved": ent_counts.get("approved", 0), "pending": ents_pending,
                         "denied": ent_counts.get("denied", 0), "expiring_within_180d": expiring},
        "go": bool(dd_total and dd_cleared == dd_total and not high_risk
                   and not ents_pending and not ent_counts.get("denied")),
    }
