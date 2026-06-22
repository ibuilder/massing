"""Data-export endpoints (guide §8) — bridges the API to the IfcOpenShell data service.
Reads the project's registered source IFC and streams XLSX. Keyed by GUID throughout."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import source_ifc_path as _source_ifc

# make the monorepo data package importable in dev (services/data/src)
_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _xlsx_bytes(sheets: dict) -> bytes:
    from aec_data.xlsx import write_sheets  # type: ignore
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        write_sheets(tmp.name, sheets)
        data = Path(tmp.name).read_bytes()
    Path(tmp.name).unlink(missing_ok=True)
    return data


def _xlsx_response(sheets: dict, filename: str) -> Response:
    return Response(
        _xlsx_bytes(sheets),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _rows_to_sheet(rows: list[dict]):
    headers = list(rows[0].keys()) if rows else []
    return headers, [[r.get(h) for h in headers] for r in rows]


@router.get("/projects/{pid}/exports/qto.xlsx")
def export_qto(pid: str, db: Session = Depends(get_db)):
    from aec_data import qto  # type: ignore

    rows = qto.takeoff_file(_source_ifc(db, pid))
    return _xlsx_response({"QTO": _rows_to_sheet(rows)}, "qto.xlsx")


@router.get("/projects/{pid}/exports/cobie.xlsx")
def export_cobie(pid: str, db: Session = Depends(get_db)):
    from aec_data import cobie  # type: ignore

    sheets = cobie.cobie_file(_source_ifc(db, pid))
    return _xlsx_response({k: _rows_to_sheet(v) for k, v in sheets.items()}, "cobie.xlsx")


@router.get("/projects/{pid}/exports/spaces.xlsx")
def export_spaces(pid: str, db: Session = Depends(get_db)):
    from aec_data import spaces  # type: ignore

    rows = spaces.space_schedule_file(_source_ifc(db, pid))
    return _xlsx_response({"Spaces": _rows_to_sheet(rows)}, "spaces.xlsx")


@router.get("/projects/{pid}/exports/schedule.xlsx")
def export_schedule(pid: str, db: Session = Depends(get_db)):
    from aec_data import schedule  # type: ignore

    acts = schedule.schedule_file(_source_ifc(db, pid))
    import json as _json

    rows = [{"id": a["id"], "name": a["name"], "start": a["start"], "finish": a["finish"],
             "element_count": len(a["guids"]), "guids": _json.dumps(a["guids"])} for a in acts]
    return _xlsx_response({"Schedule": _rows_to_sheet(rows)}, "schedule.xlsx")


_CLOSEOUT_MODULES = ("commissioning", "om_manual", "warranty", "as_built", "asset_register",
                     "completion_certificate", "punchlist")


@router.get("/projects/{pid}/closeout/package.zip")
def closeout_package(pid: str, db: Session = Depends(get_db)):
    """Turnover deliverable in one ZIP: the as-built IFC, COBie / QTO / space-schedule workbooks,
    the status-report PDF, and a JSON manifest of the closeout records (commissioning, O&M,
    warranties, as-builts, asset register, completion certificate, punchlist)."""
    import json
    import zipfile

    from .. import modules as me
    from .. import report
    from ..models import Project

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # as-built model
        if p.source_ifc and Path(p.source_ifc).exists():
            z.writestr("as-built/model.ifc", Path(p.source_ifc).read_bytes())
            try:
                from aec_data import cobie, qto, spaces  # type: ignore
                z.writestr("data/cobie.xlsx", _xlsx_bytes({k: _rows_to_sheet(v)
                           for k, v in cobie.cobie_file(p.source_ifc).items()}))
                z.writestr("data/qto.xlsx", _xlsx_bytes({"QTO": _rows_to_sheet(qto.takeoff_file(p.source_ifc))}))
                z.writestr("data/spaces.xlsx", _xlsx_bytes({"Spaces": _rows_to_sheet(spaces.space_schedule_file(p.source_ifc))}))
            except Exception as e:                # noqa: BLE001 — model exports are best-effort
                z.writestr("data/EXPORT_ERROR.txt", str(e)[:300])
        # status report
        try:
            z.writestr("report/status.pdf", report.project_status_pdf(db, pid, p.name))
        except Exception as e:                    # noqa: BLE001
            z.writestr("report/REPORT_ERROR.txt", str(e)[:300])
        # closeout records manifest
        manifest: dict = {"project": p.name, "project_id": pid, "closeout": {}}
        for mod in _CLOSEOUT_MODULES:
            if mod in me.TABLES:
                recs = me.list_records(db, mod, pid, limit=100000)
                manifest["closeout"][mod] = [{"ref": r.get("ref"), "title": r.get("title"),
                                              "status": r.get("workflow_state"), "data": r.get("data")}
                                             for r in recs]
        z.writestr("closeout/manifest.json", json.dumps(manifest, indent=2, default=str))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{p.name.replace(" ", "_")}_closeout.zip"'})
