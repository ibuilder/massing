"""Embodied-carbon endpoint — kgCO2e from the project's material quantities."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import carbon
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/carbon")
def project_carbon(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Embodied carbon (A1-A3) from `production_quantity` records: per-line kgCO2e, total tCO2e, and
    rollups by material + cost code. Built-in EPD factors (design-stage signal, not a certified LCA)."""
    return carbon.project_carbon(db, pid)


@router.get("/projects/{pid}/carbon/elements")
def carbon_elements(pid: str, gfa_m2: float | None = None,
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """CARBON-EC3: per-element A1–A3 straight off the loaded model — material category from each
    element's name/type/material psets, quantity from its own Qto sets, carbon keyed by GlobalId
    (hotspots click through to 3D). Honest coverage %: unmatched elements are excluded, never guessed.
    404 until a model is loaded."""
    from fastapi import HTTPException

    from .. import carbon_compliance
    from .properties import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project — load a model first")
    return carbon_compliance.element_carbon(idx, gfa_m2=gfa_m2)


@router.get("/projects/{pid}/carbon/compliance")
def carbon_compliance_report(pid: str, gfa_m2: float | None = None,
                             db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """CARBON-EC3: the compliance view — the Buy Clean GWP-limit check per material category (a fail =
    "this category needs a product EPD", the procurement action the program forces) + the LEED-v5-style
    A1–A3 inventory (mandatory for projects registering after 2026-07-01). 404 until a model is loaded."""
    from fastapi import HTTPException

    from .. import carbon_compliance
    from ..models import Project
    from .properties import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project — load a model first")
    result = carbon_compliance.element_carbon(idx, gfa_m2=gfa_m2)
    p = db.get(Project, pid)
    return {"elements": result,
            "buy_clean": carbon_compliance.buy_clean_check(result),
            "leed_inventory": carbon_compliance.leed_inventory(result, project_name=p.name if p else None)}
