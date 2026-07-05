"""2D documentation endpoints (Revit-style plans/sections, openBIM). Returns SVG generated
from the project source IFC by the data service."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import drawingset
from ..db import get_db
from ..deps import source_ifc_path as _source_ifc
from ..models import Project
from ..rbac import require_role

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


@router.get("/projects/{pid}/drawing-set")
def get_drawing_set(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Controlled drawing-set register from the `drawing` records: current set (latest revision per
    sheet), superseded revisions, sheet index + discipline rollup + issuance (new vs revised)."""
    return drawingset.drawing_set(db, pid)


@router.get("/projects/{pid}/drawing-set/transmittal.pdf")
def drawing_set_transmittal(pid: str, to: str = "", note: str = "", db: Session = Depends(get_db),
                            _: str = Depends(require_role("viewer"))):
    """A transmittal PDF of the controlled current set (recipients via `to`, comma-separated)."""
    reg = drawingset.drawing_set(db, pid)
    p = db.get(Project, pid)
    recipients = [r.strip() for r in to.split(",") if r.strip()]
    pdf = drawingset.transmittal_pdf(reg, p.name if p else pid, recipients, note)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="drawing-transmittal.pdf"'})


def _svg(svg: str) -> Response:
    return Response(svg.encode("utf-8"), media_type="image/svg+xml")


@router.get("/projects/{pid}/drawings/storeys")
def list_storeys(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return drawings.storey_elevations(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/drawings/plan.svg")
def plan(pid: str, elevation: float = 0.0, cut_height: float = 1.2, title: str = "PLAN",
         rooms: bool = True, callouts: bool = False, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.plan_svg(open_model(_source_ifc(db, pid)), elevation, cut_height, title,
                            rooms=rooms, callouts=callouts)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/section.svg")
def section(pid: str, axis: str = "x", offset: float = 0.0, title: str = "SECTION",
            db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.section_svg(open_model(_source_ifc(db, pid)), axis, offset, title)
    return _svg(svg)


@router.get("/projects/{pid}/drawings/elevation.svg")
def elevation(pid: str, direction: str = "north", db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
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
def sheet_svg(pid: str, sheet: str = "A-101", page: str = "A3", db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    svg = drawings.default_sheet(open_model(_source_ifc(db, pid)), _sheet_meta(db, pid, sheet),
                                 page=page, fmt="svg")
    return _svg(svg)


@router.get("/projects/{pid}/drawings/sheet.pdf")
def sheet_pdf(pid: str, sheet: str = "A-101", page: str = "A3", db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import drawings  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    pdf = drawings.default_sheet(open_model(_source_ifc(db, pid)), _sheet_meta(db, pid, sheet),
                                 page=page, fmt="pdf")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{sheet}.pdf"'})
