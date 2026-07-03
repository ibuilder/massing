"""Model-intelligence endpoints — conceptual (parametric) estimating + IFC reclassification suggestions."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from .. import conceptual_estimate as ce
from .. import ifc_classify
from ..rbac import current_user, require_role

router = APIRouter()


@router.get("/estimate/conceptual/catalog")
def conceptual_catalog(_: str = Depends(current_user)):
    """Building-type + region reference tables for the conceptual estimator."""
    return ce.catalog()


@router.post("/projects/{pid}/estimate/conceptual")
def conceptual(pid: str, params: dict = Body(...), _: str = Depends(require_role("viewer"))):
    """Conceptual (Class 5) cost from building type + GFA + units — low/base/high, escalated for
    region/year, with $/SF, $/unit, $/key metrics for the proforma."""
    return ce.estimate(params)


@router.post("/projects/{pid}/ifc/classify")
def classify(pid: str, elements: list[dict] | None = Body(default=None, embed=True),
             _: str = Depends(require_role("viewer"))):
    """Suggest IfcClass reclassifications for generic/proxy or loosely-named elements (improves QTO +
    carbon). Uses posted `elements`, or the project's loaded property index when none are given."""
    els = elements
    if not els:
        from .properties import _INDEX
        els = [{"guid": g, "name": e.get("name") or e.get("Name"),
                "ifc_class": e.get("class") or e.get("ifc_class") or e.get("type")}
               for g, e in (_INDEX.get(pid) or {}).items()]
    return ifc_classify.classify(els or [])
