"""Shared helpers for the authoring router family (REL-3 leaf split of `authoring.py`)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Project


def project_with_source(db: Session, pid: str) -> Project:
    """The project row, 404 when missing, 409 when it has no readable source IFC — the precondition
    every model-derived authoring endpoint shares."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return p


def safe_filename(name: str, fallback: str = "sheet") -> str:
    """Whitelist a download filename segment so a crafted `number` can't break out of the
    Content-Disposition quoting (defence-in-depth; the value is self-reflected only)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", name or "")[:80]
    return cleaned or fallback
