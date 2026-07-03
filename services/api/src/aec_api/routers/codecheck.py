"""Code-compliance Q&A endpoint — applicable code sections from a project description."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from starlette.concurrency import run_in_threadpool

from .. import codecheck
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
