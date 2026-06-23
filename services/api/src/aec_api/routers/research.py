"""Built-world technique endpoints (roadmap R): takt/line-of-balance planning (R2), lean PPC
analytics (R4), and research-grade benchmarks (R5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import benchmarks as bm
from .. import lean
from .. import modules as me
from .. import takt
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


class TaktIn(BaseModel):
    floors: int = Field(gt=0)
    trades: list[dict] | None = None
    jit_lead_days: int = 1


@router.post("/schedule/takt")
def schedule_takt(body: TaktIn):
    """Takt / line-of-balance plan — trades flow floor-to-floor at a steady production rate, with a
    just-in-time delivery plan (R2, the Empire State 'vertical assembly line')."""
    return takt.plan(body.floors, body.trades, jit_lead_days=body.jit_lead_days)


@router.get("/benchmarks")
def get_benchmarks():
    """Citable benchmark ranges (cost/sf, cap rates, productivity, lean PPC) for grounding defaults (R5)."""
    return bm.all_benchmarks()


@router.get("/projects/{pid}/schedule/4d")
def schedule_4d(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """4D construction sequence (C3): map the published model's elements onto a takt plan derived
    from the storey count, returning scrubable timeline frames (cumulative % built per day)."""
    import json

    from .. import fourd, storage, takt
    try:
        idx = json.loads(storage.get(f"{pid}/props.json"))
        elements = idx.get("elements", [])
    except Exception:                                # noqa: BLE001 — no published index yet
        elements = []
    floors = max([fourd._floor_index(e.get("storey")) for e in elements] + [0]) + 1
    plan = takt.plan(floors)
    return {"floors": floors, "duration_days": plan["duration_days"], **fourd.timeline(plan, elements)}


@router.get("/projects/{pid}/lean/ppc")
def lean_ppc(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Last-Planner Plan Percent Complete + reasons for non-completion from the weekly-plan module (R4)."""
    records = me.list_records(db, "weekly_plan", pid, limit=1_000_000) if "weekly_plan" in me.TABLES else []
    return lean.ppc(records)
