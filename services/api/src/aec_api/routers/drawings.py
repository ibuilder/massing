"""2D documentation endpoints (Revit-style plans/sections, openBIM). Returns SVG generated
from the project source IFC by the data service."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _source_ifc(db: Session, pid: str) -> str:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc or not Path(p.source_ifc).exists():
        raise HTTPException(409, "project has no accessible source IFC")
    return p.source_ifc


def _svg(svg: str) -> Response:
    return Response(svg.encode("utf-8"), media_type="image/svg+xml")


@router.get("/projects/{pid}/drawings/storeys")
def list_storeys(pid: str, db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return drawings.storey_elevations(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/drawings/plan.svg")
def plan(pid: str, elevation: float = 0.0, cut_height: float = 1.2, title: str = "PLAN",
         db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.plan_svg(open_model(_source_ifc(db, pid)), elevation, cut_height, title)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/section.svg")
def section(pid: str, axis: str = "x", offset: float = 0.0, title: str = "SECTION",
            db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.section_svg(open_model(_source_ifc(db, pid)), axis, offset, title)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/elevation.svg")
def elevation(pid: str, direction: str = "north", db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.elevation(open_model(_source_ifc(db, pid)), direction,
                             f"{direction.upper()} ELEVATION")
    return _svg(svg)


def _sheet_meta(db: Session, pid: str, sheet: str) -> dict:
    from datetime import date

    p = db.get(Project, pid)
    return {"project": (p.name if p else "PROJECT").upper(), "sheet": sheet,
            "date": date.today().isoformat(), "drawn_by": "AEC Platform"}


@router.get("/projects/{pid}/drawings/sheet.svg")
def sheet_svg(pid: str, sheet: str = "A-101", page: str = "A3", db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.default_sheet(open_model(_source_ifc(db, pid)), _sheet_meta(db, pid, sheet),
                                 page=page, fmt="svg")
    return _svg(svg)


@router.get("/projects/{pid}/drawings/sheet.pdf")
def sheet_pdf(pid: str, sheet: str = "A-101", page: str = "A3", db: Session = Depends(get_db)):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    pdf = drawings.default_sheet(open_model(_source_ifc(db, pid)), _sheet_meta(db, pid, sheet),
                                 page=page, fmt="pdf")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{sheet}.pdf"'})
