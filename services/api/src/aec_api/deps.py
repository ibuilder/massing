"""Shared FastAPI dependencies / helpers used across routers (DRY)."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Project


def get_project(db: Session, pid: str) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p


def source_ifc_path(db: Session, pid: str) -> str:
    """Path to the project's source IFC, or 409 if not set/accessible."""
    p = get_project(db, pid)
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC (set project.source_ifc)")
    return p.source_ifc


def open_source_ifc(db: Session, pid: str):
    """Open the project's source IFC as an ifcopenshell model — 409 if unset/missing, 400 if unreadable.

    The single resolve-then-open path several analysis endpoints share (A3): a missing model is a 409,
    a corrupt/unparseable file is a 4xx not a 500. Returns an `ifcopenshell.file`.
    """
    path = source_ifc_path(db, pid)  # raises 409 if unset/missing
    import ifcopenshell  # type: ignore  # deferred — heavy native import, keep out of module load

    try:
        return ifcopenshell.open(path)
    except Exception as e:  # noqa: BLE001 — a bad file is a 4xx, not a 500
        raise HTTPException(400, f"could not read the IFC: {e}") from e
