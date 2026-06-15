"""Real-estate development finance (Proforma) endpoints: stateless solve + scenario CRUD.
The pure engine (aec_api.proforma) is validated by Pydantic models that double as the
OpenAPI contract. A full proforma + waterfall solves in <100ms — run it in-request."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Scenario
from ..proforma.solve import solve

router = APIRouter()


# --- input contract (validation + docs) -------------------------------------
class Timing(BaseModel):
    construction_months: int = Field(gt=0)
    leaseup_months: int = 0
    hold_years: float = Field(gt=0)
    start_date: str | None = None


class CostLine(BaseModel):
    category: Literal["land", "hard", "soft", "contingency", "fee"]
    name: str
    amount: float = 0
    curve: Literal["scurve", "linear", "upfront"] = "scurve"
    start_month: int = 0
    end_month: int = 0
    csi_code: str | None = None


class Debt(BaseModel):
    ltc: float = Field(ge=0, le=1)
    rate: float = Field(ge=0)
    points: float = 0.0
    funding: Literal["equity_first", "pari_passu", "loan_first"] = "equity_first"


class Equity(BaseModel):
    lp_pct: float = Field(ge=0, le=1)
    gp_pct: float = Field(ge=0, le=1)


class Ops(BaseModel):
    potential_rent_annual: float
    other_income_annual: float = 0
    opex_annual: float
    stabilized_occ: float = Field(gt=0, le=1)
    credit_loss_pct: float = 0.0


class Exit(BaseModel):
    exit_cap: float = Field(gt=0)
    selling_cost_pct: float = 0.0


class Tier(BaseModel):
    hurdle: float | None = None
    lp: float
    gp: float


class Waterfall(BaseModel):
    pref_rate: float = 0.08
    style: Literal["american", "european"] = "american"
    clawback: bool = False
    tiers: list[Tier]


class Assumptions(BaseModel):
    timing: Timing
    cost_lines: list[CostLine]
    debt: Debt
    equity: Equity
    operations: Ops
    exit: Exit
    waterfall: Waterfall
    discount_rate: float = 0.10


@router.post("/proforma/solve")
def solve_stateless(a: Assumptions):
    """Solve a deal without persisting — full S&U, cash flows, returns, waterfall."""
    return solve(a.model_dump())


# --- scenarios (persisted, versioned) ---------------------------------------
class ScenarioIn(BaseModel):
    name: str
    project_id: str | None = None
    assumptions: Assumptions


@router.post("/proforma/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, db: Session = Depends(get_db)):
    result = solve(body.assumptions.model_dump())
    s = Scenario(name=body.name, project_id=body.project_id,
                 assumptions=body.assumptions.model_dump(), result=result)
    db.add(s)
    db.commit()
    return {"id": s.id, "name": s.name, "result": result}


@router.get("/proforma/scenarios")
def list_scenarios(project_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Scenario)
    if project_id:
        q = q.filter(Scenario.project_id == project_id)
    return [{"id": s.id, "name": s.name, "project_id": s.project_id,
             "returns": (s.result or {}).get("returns")} for s in q.order_by(Scenario.created_at).all()]


@router.get("/proforma/scenarios/{sid}")
def get_scenario(sid: str, db: Session = Depends(get_db)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    return {"id": s.id, "name": s.name, "assumptions": s.assumptions, "result": s.result}


@router.put("/proforma/scenarios/{sid}")
def update_scenario(sid: str, body: ScenarioIn, db: Session = Depends(get_db)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    if s.is_locked:
        raise HTTPException(409, "scenario is locked")
    s.assumptions = body.assumptions.model_dump()
    s.name = body.name
    s.result = solve(s.assumptions)
    db.commit()
    return {"id": s.id, "name": s.name, "result": s.result}


@router.post("/proforma/scenarios/{sid}/clone", status_code=201)
def clone_scenario(sid: str, name: str = Body(..., embed=True), db: Session = Depends(get_db)):
    s = db.get(Scenario, sid)
    if not s:
        raise HTTPException(404, "scenario not found")
    c = Scenario(name=name, project_id=s.project_id, assumptions=s.assumptions, result=s.result)
    db.add(c)
    db.commit()
    return {"id": c.id, "name": c.name}


@router.post("/proforma/compare")
def compare(ids: list[str] = Body(...), db: Session = Depends(get_db)):
    """Side-by-side metrics for several scenarios."""
    out = []
    for sid in ids:
        s = db.get(Scenario, sid)
        if s and s.result:
            out.append({"id": s.id, "name": s.name, "returns": s.result.get("returns"),
                        "sources_uses": s.result.get("sources_uses")})
    return out
