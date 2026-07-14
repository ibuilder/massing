"""Code-compliance endpoints — applicable code sections from a project description (LLM/rules), and a
computed occupancy-load + egress-capacity pre-check over the model (W9-2)."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import codecheck
from ..db import get_db
from ..models import Project
from ..rbac import require_role
from ..throttle import rate_limited

router = APIRouter()
_throttle = rate_limited("draft", 30)          # LLM call when a key is set


@router.post("/projects/{pid}/codecheck")
async def code_check(pid: str, description: str = Body("", embed=True),
                     context: str | None = Body(None, embed=True),
                     _: str = Depends(require_role("viewer")), __: None = Depends(_throttle)):
    """Applicable IBC/ADA/IECC provisions (code + section + requirement) for the described project.
    Claude when an API key is set; a deterministic IBC checklist otherwise. Always confirm with the AHJ."""
    return await run_in_threadpool(codecheck.check, description, context)


@router.get("/projects/{pid}/codecheck/egress")
def codecheck_egress(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W9-2: COMPUTED occupancy load (IBC 1004) + egress capacity (IBC 1005) from the model's
    IfcSpaces/IfcDoors — the depth layer above the presence-only /elements/code-check. Reads spaces
    straight from the source IFC (they aren't in the physical-element index). Pre-check assist with
    cited IBC sections; NOT a certified review."""
    from aec_data.ifc_loader import open_model  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — occupancy/egress needs a model with IfcSpaces")
    return codecheck.egress_from_model(open_model(p.source_ifc))
