"""Generative design (Phase 6+): turn a municipal zoning envelope into a real IFC model + a
basic acquisition proforma. This is the IFC-native answer to TestFit/Forma feasibility — the
output is openBIM, so the same model flows into the viewer, drawings, QTO, the estimate, and the
proforma underwriting (areas → hard cost / rent). One click goes lot → building → deal.

Math lives in aec_data.massing (pure, unit-tested); this router wires it to a project: generate
the IFC, set it as the project's source of truth, publish (convert→.frag + reindex) off-thread,
and solve a starter acquisition proforma seeded from the generated program."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, storage
from ..db import get_db
from ..models import Project
from ..proforma.solve import solve
from ..rbac import require_role
from .authoring import _DATA_SRC, _IFC_DIR, _publish_bg

if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()

M2_TO_SF = 10.7639


class MassingIn(BaseModel):
    """Zoning envelope (metres) + acquisition assumptions for the starter proforma."""
    name: str = "Massing Study"
    use_type: str = "residential"          # residential | commercial
    # --- zoning envelope ---
    lot_width: float | None = Field(default=None, gt=0)
    lot_depth: float | None = Field(default=None, gt=0)
    lot_area: float | None = Field(default=None, gt=0)        # use if width/depth unknown
    lot_polygon: list[list[float]] | None = Field(default=None)  # real parcel [[x,y],…] in metres
    far: float = Field(default=2.0, gt=0)
    coverage_max: float = Field(default=0.6, gt=0, le=1)
    front_setback: float = Field(default=6.0, ge=0)
    rear_setback: float = Field(default=6.0, ge=0)
    side_setback: float = Field(default=3.0, ge=0)
    height_limit: float | None = Field(default=None, gt=0)
    floor_to_floor: float = Field(default=3.5, gt=0)
    efficiency: float = Field(default=0.82, gt=0, le=1)       # GFA → net sellable/leasable
    avg_unit_m2: float = Field(default=75.0, ge=0)            # for unit count (residential)
    frame: bool = Field(default=False)                        # also generate a concrete structural frame
    bay_m: float = Field(default=7.5, gt=2)                   # column-grid bay spacing (m)
    units: bool = Field(default=False)                        # subdivide floors into per-unit spaces
    envelope: bool = Field(default=False)                     # wrap floors in facade walls + windows
    wwr: float = Field(default=0.4, gt=0, le=0.95)            # window-to-wall ratio
    core: bool = Field(default=False)                         # service core: shafts + stair + MEP risers
    unit_layout: str = Field(default="grid")                  # "grid" | "corridor" (double-loaded test-fit)
    # --- acquisition proforma seed ---
    land_cost: float = Field(default=2_500_000.0, ge=0)
    hard_cost_psf: float = Field(default=225.0, ge=0)         # $/sf GFA
    soft_cost_pct: float = Field(default=0.15, ge=0)          # of hard
    contingency_pct: float = Field(default=0.05, ge=0)        # of hard
    rent_per_unit_month: float = Field(default=3000.0, ge=0)  # residential
    rent_psf_year: float = Field(default=38.0, ge=0)          # commercial $/sf/yr
    opex_ratio: float = Field(default=0.35, ge=0, le=1)       # of effective gross income
    exit_cap: float = Field(default=0.05, gt=0)
    ltc: float = Field(default=0.6, ge=0, le=1)
    rate: float = Field(default=0.075, ge=0)


def _proforma_seed(p: MassingIn, m: dict) -> dict:
    """Build a starter Assumptions payload from the generated program, then solve it. Numbers are
    transparent defaults the underwriter overrides — the point is an instant lot→deal first cut."""
    gfa_sf = m["buildable_gfa_sf"]
    hard = gfa_sf * p.hard_cost_psf
    if p.use_type == "commercial":
        net_lsf = m["net_sellable_m2"] * M2_TO_SF
        pgi = net_lsf * p.rent_psf_year
    else:
        pgi = m["units"] * p.rent_per_unit_month * 12
    assumptions = {
        "timing": {"construction_months": 18, "leaseup_months": 6, "hold_years": 5},
        "cost_lines": [
            {"category": "land", "name": "Land acquisition", "amount": p.land_cost, "curve": "upfront"},
            {"category": "hard", "name": "Hard costs", "amount": round(hard), "curve": "scurve"},
            {"category": "soft", "name": "Soft costs", "amount": round(hard * p.soft_cost_pct), "curve": "linear"},
            {"category": "contingency", "name": "Contingency", "amount": round(hard * p.contingency_pct), "curve": "scurve"},
        ],
        "debt": {"ltc": p.ltc, "rate": p.rate},
        "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
        "operations": {
            "potential_rent_annual": round(pgi),
            "opex_annual": round(pgi * p.opex_ratio),
            "stabilized_occ": 0.95,
            "credit_loss_pct": 0.02,
        },
        "exit": {"exit_cap": p.exit_cap, "selling_cost_pct": 0.02},
        "waterfall": {"pref_rate": 0.08, "style": "american",
                      "tiers": [{"hurdle": None, "lp": 0.8, "gp": 0.2}]},
        "discount_rate": 0.10,
    }
    try:
        result = solve(assumptions)
    except Exception as e:  # noqa: BLE001 — proforma is a bonus; never fail the generate
        return {"assumptions": assumptions, "solve_error": str(e)[:200]}
    return {"assumptions": assumptions,
            "returns": result.get("returns"), "sources_uses": result.get("sources_uses")}


@router.post("/projects/{pid}/generate/massing")
def generate_massing(pid: str, body: MassingIn, db: Session = Depends(get_db),
                     actor: str = Depends(require_role("editor"))):
    """Generate an IFC massing model from a zoning envelope, set it as the project's source IFC,
    publish it (off-thread), and return the buildable program + a starter acquisition proforma."""
    from aec_data.massing import compute_massing, generate_ifc  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    try:
        metrics = compute_massing(body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))

    _IFC_DIR.joinpath(pid).mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / pid / "source.ifc"
    generate_ifc(metrics, str(ifc_path), name=body.name, frame=body.frame, bay=body.bay_m,
                 units=body.units, envelope=body.envelope, wwr=body.wwr, core=body.core,
                 unit_layout=body.unit_layout)
    metrics["framed"] = body.frame
    metrics["unitized"] = body.units
    metrics["enclosed"] = body.envelope
    metrics["cored"] = body.core
    storage.put(f"{pid}/source.ifc", ifc_path.read_bytes())   # durable copy
    p.source_ifc = str(ifc_path)
    db.commit()
    audit.record(db, action="ifc.generate", actor=actor, method="POST",
                 path=f"/projects/{pid}/generate/massing", detail=metrics)
    db.commit()

    _publish_bg(pid)                                            # convert→.frag + reindex off-thread
    return {"metrics": metrics, "proforma": _proforma_seed(body, metrics),
            "source_ifc": str(ifc_path), "publish": "running"}


class TestFitIn(BaseModel):
    """Fit a unit mix to a floor plate and compare schemes (TestFit-style)."""
    plate_w: float = Field(gt=0)
    plate_d: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    schemes: list[dict] = Field(default_factory=list)   # [{name, unit_types?, parking_ratio?, parking_kind?}]


@router.post("/test-fit/compare")
def test_fit_compare(body: TestFitIn):
    """Compare unit-mix schemes on a floor plate — yield metrics (units, efficiency, NSF/GSF, mix)
    + parking — ranked so you can find the scheme that pencils. Stateless; the rects also feed the
    IFC massing generator (unit_layout='corridor')."""
    from .. import test_fit as tf
    schemes = body.schemes or [
        {"name": "Efficient (more 1BR)", "unit_types": [
            {"name": "Studio", "target_sf": 480, "mix_pct": 0.3},
            {"name": "1BR", "target_sf": 720, "mix_pct": 0.55},
            {"name": "2BR", "target_sf": 1000, "mix_pct": 0.15}], "parking_ratio": 1.0},
        {"name": "Balanced", "unit_types": None, "parking_ratio": 1.2},
        {"name": "Family (more 2BR)", "unit_types": [
            {"name": "1BR", "target_sf": 780, "mix_pct": 0.35},
            {"name": "2BR", "target_sf": 1100, "mix_pct": 0.45},
            {"name": "3BR", "target_sf": 1400, "mix_pct": 0.2}], "parking_ratio": 1.5},
    ]
    return tf.compare(body.plate_w, body.plate_d, body.floors, schemes)


class OptimizeIn(BaseModel):
    """Generative design: sweep schemes and rank by an objective, filtered by targets."""
    plate_w: float = Field(gt=0)
    plate_d: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    targets: dict = Field(default_factory=dict)   # min_units, min_efficiency, max_parking_ratio, min_yoc, objective
    econ: dict = Field(default_factory=dict)       # rent_psf_yr, hard_psf, stall_cost, opex_ratio, land


@router.post("/test-fit/optimize")
def test_fit_optimize(body: OptimizeIn):
    """Generative design — sweep unit-mix × parking presets, filter by targets, rank by yield-on-cost
    (or another objective). Returns the ranked feasible schemes + the winner ("find the deal that
    pencils")."""
    from .. import test_fit as tf
    return tf.optimize(body.plate_w, body.plate_d, body.floors, body.targets, body.econ)


@router.post("/generate/massing/preview")
def preview_massing(body: MassingIn):
    """Compute the program + proforma WITHOUT writing an IFC or touching a project — for the
    'what would this lot yield?' form before committing to a model. Stateless, instant."""
    try:
        metrics = compute_massing_only(body)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"metrics": metrics, "proforma": _proforma_seed(body, metrics)}


def compute_massing_only(body: MassingIn) -> dict:
    from aec_data.massing import compute_massing  # type: ignore
    return compute_massing(body.model_dump())
