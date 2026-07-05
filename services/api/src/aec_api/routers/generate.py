"""Generative design (Phase 6+): turn a municipal zoning envelope into a real IFC model + a
basic acquisition proforma. IFC-native generative feasibility — the output is openBIM, so the same
model flows into the viewer, drawings, QTO, the estimate, and the proforma underwriting (areas →
hard cost / rent). One click goes lot → building → deal.

Math lives in aec_data.massing (pure, unit-tested); this router wires it to a project: generate
the IFC, set it as the project's source of truth, publish (convert→.frag + reindex) off-thread,
and solve a starter acquisition proforma seeded from the generated program."""
from __future__ import annotations

import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import audit, design_phase, soft_costs, storage
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
    shape: str = "box"                     # box | dome (monolithic / earth dome house)
    dome_radius: float = Field(default=8.0, gt=0)   # hemisphere radius (m), for shape="dome"
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
    parking: int = Field(default=0, ge=0, le=2000)            # surface parking stalls as real IfcSpaces (A2)
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
            # itemized soft costs (A/E design fee, permits, legal, financing, insurance, developer fee,
            # FF&E, marketing, soft contingency) — totals hard × soft_cost_pct, phase-aware A/E fee.
            *soft_costs.proforma_cost_lines(hard, p.soft_cost_pct * 100),
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


def _seed_dev_budget(body: "MassingIn", m: dict) -> dict:
    """A starter B1 cost budget from the generated program, so Sources & Uses / Finance show the real
    deal immediately after generate (land + hard from GFA×$/sf + soft) instead of a $0 template."""
    hard = float(m.get("buildable_gfa_sf", 0)) * body.hard_cost_psf
    return {"lines": [
        {"category": "acquisition", "description": "Land acquisition", "unit_cost": float(body.land_cost), "quantity": 1, "cost_code": ""},
        {"category": "hard", "description": "Hard costs (GFA × $/sf)", "unit_cost": round(hard), "quantity": 1, "cost_code": ""},
        # itemized soft costs (A/E fee, permits, legal, financing, insurance, developer fee, FF&E, …)
        *soft_costs.budget_lines(hard, body.soft_cost_pct * 100),
    ]}


def _seed_spine_skeleton(db, pid: str, cc: dict, cc_budget: dict, actor: str) -> dict:
    """Discipline Spine skeleton (D5): a bid package per discipline linked to its cost code, and a spec
    section per division linked to that package — so a generated project is traceable end to end
    (discipline → specs → bid package → cost code → budget) the moment it's created. Reuses the D1
    classification vocabulary for the division titles."""
    from .. import classification as cls
    from .. import modules as me
    if "bid_package" not in me.TABLES or "spec_section" not in me.TABLES:
        return {"seeded": False}
    # discipline -> (primary cost-code key, the divisions it procures, its spec sections)
    plan = [
        ("Structural", "03-3000", ["03-3000", "05-1000"],
         [("03 30 00", "Cast-in-Place Concrete", "03"), ("05 12 00", "Structural Steel Framing", "05")]),
        ("Architectural", "09-0000", ["09-0000"], [("09 29 00", "Gypsum Board Assemblies", "09")]),
        ("Mechanical", "23-0000", ["23-0000"], [("23 00 00", "Heating, Ventilating & Air Conditioning", "23")]),
        ("Electrical", "26-0000", ["26-0000"], [("26 00 00", "Electrical", "26")]),
    ]
    packages = specs = 0
    for disc, primary, codes, sections in plan:
        if primary not in cc:
            continue
        budget = sum(cc_budget.get(c, 0) for c in codes)
        bp = me.create_record(db, "bid_package", pid, {"data": {
            "name": f"{disc} package", "trade": disc, "discipline": disc,
            "cost_code": cc[primary], "budget": budget}}, actor, "GC")
        packages += 1
        for num, title, div in sections:
            me.create_record(db, "spec_section", pid, {"data": {
                "section_number": num, "title": title,
                "division": f"{div} — {cls.MF_DIVISIONS.get(div, '')}".strip(" —"),
                "discipline": disc, "bid_package": bp["id"]}}, actor, "GC")
            specs += 1
    return {"seeded": True, "bid_packages": packages, "spec_sections": specs}


def _seed_gc_portal(db, pid: str, body: "MassingIn", m: dict, actor: str) -> dict:
    """Seed the GC portal so a generated project is complete across all three pillars (model · GC ·
    deal), not just the proforma: CSI cost codes, a hard-cost-allocated budget, a GMP prime contract
    (value = hard cost, so it reconciles in-sync with the underwriting), and a cost-loaded schedule
    of structure activities by floor. Idempotent — skips if cost codes already exist."""
    from datetime import date, timedelta

    from .. import modules as me
    if "cost_code" not in me.TABLES or me.list_records(db, "cost_code", pid, limit=1):
        return {"seeded": False}
    hard = round(float(m.get("buildable_gfa_sf", 0)) * body.hard_cost_psf)
    if hard <= 0:
        return {"seeded": False}
    # CSI divisions and their share of hard cost (sums to 1.0)
    divisions = [("01-0000", "General Requirements", "01", 0.10), ("03-3000", "Concrete", "03", 0.28),
                 ("05-1000", "Structural Steel", "05", 0.18), ("23-0000", "HVAC", "23", 0.12),
                 ("26-0000", "Electrical", "26", 0.13), ("09-0000", "Finishes", "09", 0.19)]
    cc = {}
    cc_budget = {}
    for code, desc, div, frac in divisions:
        r = me.create_record(db, "cost_code", pid, {"data": {"code": code, "description": desc, "division": div}}, actor, "GC")
        cc[code] = r["id"]
        cc_budget[code] = round(hard * frac)
        me.create_record(db, "budget", pid, {"data": {"cost_code": r["id"], "description": desc, "revised": cc_budget[code]}}, actor, "GC")
    _seed_spine_skeleton(db, pid, cc, cc_budget, actor)
    me.create_record(db, "prime_contract", pid, {"data": {
        "name": "GMP w/ Owner", "type": "GMP", "value": hard,
        "overhead_pct": 5, "fee_pct": 4, "contingency_pct": 3}}, actor, "GC")
    # cost-loaded structure activities, one per floor, spread over the build
    floors = max(1, int(m.get("floors") or 1))
    struct_budget = hard * 0.46                         # concrete + steel
    start, per = date.today(), 21
    acts = 0
    for f in range(1, floors + 1):
        s = start + timedelta(days=(f - 1) * per)
        me.create_record(db, "schedule_activity", pid, {"data": {
            "name": f"Structure L{f}", "trade": "Structure", "start": s.isoformat(),
            "finish": (s + timedelta(days=per + 7)).isoformat(),
            "budget": round(struct_budget / floors), "cost_code": cc["03-3000"], "percent": 0}}, actor, "GC")
        acts += 1
    return {"seeded": True, "cost_codes": len(divisions), "activities": acts, "gmp": hard}


@router.post("/projects/{pid}/generate/massing")
def generate_massing(pid: str, body: MassingIn, db: Session = Depends(get_db),
                     actor: str = Depends(require_role("editor"))):
    """Generate an IFC massing model from a zoning envelope, set it as the project's source IFC,
    publish it (off-thread), and return the buildable program + a starter acquisition proforma."""
    from aec_data.massing import compute_massing, dome_metrics, generate_dome_ifc, generate_ifc  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")

    _IFC_DIR.joinpath(pid).mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / pid / "source.ifc"

    if body.shape == "dome":
        # monolithic / earth dome — hemispherical shell (no zoning math; sized by radius)
        metrics = dome_metrics(body.dome_radius, body.efficiency, body.avg_unit_m2)
        generate_dome_ifc(str(ifc_path), name=body.name, radius=body.dome_radius)
        metrics["framed"] = metrics["unitized"] = metrics["enclosed"] = metrics["cored"] = False
        metrics["structure"] = {"system": "Monolithic dome shell", "rationale":
                                "A thin reinforced shell carries load in compression — no separate frame."}
        storage.put(f"{pid}/source.ifc", ifc_path.read_bytes())
        p.source_ifc = str(ifc_path)
        if not p.dev_budget:                                   # seed Finance so it isn't $0 after generate
            p.dev_budget = _seed_dev_budget(body, metrics)
        db.commit()
        audit.record(db, action="ifc.generate", actor=actor, method="POST",
                     path=f"/projects/{pid}/generate/massing", detail=metrics)
        db.commit()
        gc_seed = _seed_gc_portal(db, pid, body, metrics, actor)
        design_phase.seed_phases(db, pid, actor)           # lay the 8 RIBA/AIA design phases
        _publish_bg(pid)
        return {"metrics": metrics, "proforma": _proforma_seed(body, metrics), "gc_seed": gc_seed,
                "source_ifc": str(ifc_path), "publish": "running"}

    try:
        metrics = compute_massing(body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))

    # R3: pick a plausible structural system + member sizes for the building's scale
    from .. import structure as st
    rec = st.recommend(metrics["building_height_m"], metrics["floors"], body.bay_m, body.use_type)
    mm = rec["members_mm"]
    members = {"slab_m": mm["slab"] / 1000, "column_m": mm["column"] / 1000,
               "beam_depth_m": mm["beam_depth"] / 1000, "beam_width_m": max(0.3, mm["beam_depth"] / 1000 * 0.6)}

    generate_ifc(metrics, str(ifc_path), name=body.name, frame=body.frame, bay=body.bay_m,
                 units=body.units, envelope=body.envelope, wwr=body.wwr, core=body.core,
                 unit_layout=body.unit_layout, members=members, parking=body.parking)
    metrics["framed"] = body.frame
    metrics["unitized"] = body.units
    metrics["enclosed"] = body.envelope
    metrics["cored"] = body.core
    metrics["parking_stalls"] = body.parking
    metrics["structure"] = rec
    storage.put(f"{pid}/source.ifc", ifc_path.read_bytes())   # durable copy
    p.source_ifc = str(ifc_path)
    if not p.dev_budget:                                       # seed Finance so it isn't $0 after generate
        p.dev_budget = _seed_dev_budget(body, metrics)
    db.commit()
    audit.record(db, action="ifc.generate", actor=actor, method="POST",
                 path=f"/projects/{pid}/generate/massing", detail=metrics)
    db.commit()
    gc_seed = _seed_gc_portal(db, pid, body, metrics, actor)    # complete the GC pillar too
    design_phase.seed_phases(db, pid, actor)                   # lay the 8 RIBA/AIA design phases

    _publish_bg(pid)                                            # convert→.frag + reindex off-thread
    return {"metrics": metrics, "proforma": _proforma_seed(body, metrics), "gc_seed": gc_seed,
            "source_ifc": str(ifc_path), "publish": "running"}


class StructureIn(BaseModel):
    """Structural-system advice for a given scale."""
    height_m: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    span_m: float = Field(default=7.5, gt=0)
    use_type: str = "residential"


@router.post("/structure/recommend")
def structure_recommend(body: StructureIn):
    """Recommend a structural system + rough member sizes + load path for a building's scale (R3,
    Salvadori). Stateless; the same advisor drives the generated frame's member sizing."""
    from .. import structure as st
    return st.recommend(body.height_m, body.floors, body.span_m, body.use_type)


# standard comparison schemes used when the caller passes none (and, with with_defaults, alongside a
# caller's custom mix so a user-defined unit mix is ranked against the familiar presets)
_DEFAULT_SCHEMES = [
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


class TestFitIn(BaseModel):
    """Fit a unit mix to a floor plate and compare schemes (TestFit-style)."""
    plate_w: float = Field(gt=0)
    plate_d: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    schemes: list[dict] = Field(default_factory=list)   # [{name, unit_types?, parking_ratio?, parking_kind?}]
    with_defaults: bool = False                          # also rank the preset schemes (A1b custom-mix compare)


@router.post("/test-fit/compare")
def test_fit_compare(body: TestFitIn):
    """Compare unit-mix schemes on a floor plate — yield metrics (units, efficiency, NSF/GSF, mix)
    + parking — ranked so you can find the scheme that pencils. Stateless; the rects also feed the
    IFC massing generator (unit_layout='corridor')."""
    from .. import test_fit as tf
    schemes = body.schemes or _DEFAULT_SCHEMES
    if body.schemes and body.with_defaults:          # rank the custom mix against the presets
        schemes = body.schemes + _DEFAULT_SCHEMES
    return tf.compare(body.plate_w, body.plate_d, body.floors, schemes)


class OptimizeIn(BaseModel):
    """Generative design: sweep schemes and rank by an objective, filtered by targets."""
    plate_w: float = Field(gt=0)
    plate_d: float = Field(gt=0)
    floors: int = Field(default=1, ge=1)
    targets: dict = Field(default_factory=dict)   # min_units, min_efficiency, max_parking_ratio, min_yoc, objective
    econ: dict = Field(default_factory=dict)       # rent_psf_yr, hard_psf, stall_cost, opex_ratio, land
    pid: str | None = None                         # if set, pull live project land + hard $/sf (U6)


@router.post("/test-fit/optimize")
def test_fit_optimize(body: OptimizeIn, db: Session = Depends(get_db)):
    """Generative design — sweep unit-mix × parking presets, filter by targets, rank by yield-on-cost
    (or another objective). With `pid`, seed the econ from the project's real land price + cost budget
    so the ranking reflects the actual deal, not a generic proxy (U6)."""
    from .. import test_fit as tf
    econ = dict(body.econ)
    if body.pid:
        from ..models import Project as _P
        p = db.get(_P, body.pid)
        if p:
            prop = (p.dev_property or {})
            if prop.get("purchase_price"):
                econ.setdefault("land", float(prop["purchase_price"]))
            # hard $/sf from the cost budget's hard line, if the user keyed one
            for ln in ((p.dev_budget or {}).get("lines") or []):
                if ln.get("category") == "hard" and ln.get("unit_cost") and ln.get("quantity", 1) and "sf" in (ln.get("description") or "").lower():
                    econ.setdefault("hard_psf", float(ln["unit_cost"])); break
    return tf.optimize(body.plate_w, body.plate_d, body.floors, body.targets, econ)


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
