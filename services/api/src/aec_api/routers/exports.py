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
from ..rbac import require_role

# make the monorepo data package importable in dev (services/data/src)
_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _xlsx_bytes(sheets: dict) -> bytes:
    import tempfile

    from aec_data.xlsx import write_sheets  # type: ignore

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        write_sheets(tmp.name, sheets)
        data = Path(tmp.name).read_bytes()
    Path(tmp.name).unlink(missing_ok=True)
    return data


def safe_filename(name: str, fallback: str = "project") -> str:
    """An ASCII/latin-1-safe filename for Content-Disposition. HTTP headers are latin-1 encoded, so a
    project name with an em-dash, smart quote, accent or emoji would crash the download (500); collapse
    anything outside a safe set to '_'."""
    out = "".join(c if (c.isalnum() and ord(c) < 128) or c in "-_ ." else "_" for c in (name or "")).strip()
    return out or fallback


def _xlsx_response(sheets: dict, filename: str) -> Response:
    return Response(
        _xlsx_bytes(sheets),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename(filename, "export.xlsx")}"'},
    )


def _rows_to_sheet(rows: list[dict]):
    # union of keys across all rows (order-preserving) so merged sheets from >1 source keep every
    # column, not just those on the first row.
    headers = list(dict.fromkeys(k for r in rows for k in r.keys()))
    return headers, [[r.get(h) for h in headers] for r in rows]


def _merge_sheets(*sources: dict) -> dict:
    """Combine {sheet: rows} dicts, concatenating rows for same-named sheets (e.g. a model-derived
    COBie System + the commissioning-derived System) instead of one clobbering the other."""
    out: dict[str, list[dict]] = {}
    for src in sources:
        for name, rows in src.items():
            out.setdefault(name, []).extend(rows)
    return out


@router.get("/projects/{pid}/exports/qto.xlsx")
def export_qto(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import qto  # type: ignore

    rows = qto.takeoff_file(_source_ifc(db, pid))
    return _xlsx_response({"QTO": _rows_to_sheet(rows)}, "qto.xlsx")


def _closeout_cobie_sheets(db, pid: str) -> dict:
    """COBie workbook tabs built from the closeout modules (DB, not the IFC): Warranty, System
    (commissioning), Asset (asset register), Document (O&M manuals) — folding turnover data into
    the same deliverable as the model-derived Facility/Space/Type/Component sheets."""
    from .. import modules as me

    def recs(mod):
        return me.list_records(db, mod, pid, limit=1_000_000) if mod in me.TABLES else []

    def col(r, *keys):
        d = r.get("data") or {}
        return next((d[k] for k in keys if d.get(k)), None)

    sheets: dict = {}
    w = [{"Name": r.get("title") or col(r, "name"), "Vendor": col(r, "vendor"),
          "ExpiresDate": col(r, "expires"), "Asset": col(r, "asset")} for r in recs("warranty")]
    if w:
        sheets["Warranty"] = w
    sysr = [{"Name": r.get("title") or col(r, "system"), "Status": r.get("workflow_state")} for r in recs("commissioning")]
    if sysr:
        sheets["System"] = sysr
    asr = [{"Name": r.get("title") or col(r, "name"), "Tag": col(r, "tag", "asset_tag"),
            "Location": col(r, "location")} for r in recs("asset_register")]
    if asr:
        sheets["Asset"] = asr
    docs = [{"Name": r.get("title") or col(r, "name"), "Category": "O&M Manual"} for r in recs("om_manual")]
    if docs:
        sheets["Document"] = docs
    return sheets


@router.get("/projects/{pid}/exports/cobie.xlsx")
def export_cobie(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import cobie  # type: ignore

    merged = _merge_sheets(cobie.cobie_file(_source_ifc(db, pid)), _closeout_cobie_sheets(db, pid))
    sheets = {k: _rows_to_sheet(v) for k, v in merged.items()}
    return _xlsx_response(sheets, "cobie.xlsx")


@router.get("/projects/{pid}/exports/spaces.xlsx")
def export_spaces(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import spaces  # type: ignore

    rows = spaces.space_schedule_file(_source_ifc(db, pid))
    return _xlsx_response({"Spaces": _rows_to_sheet(rows)}, "spaces.xlsx")


@router.get("/projects/{pid}/exports/model.gbxml")
def export_gbxml(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """gbXML (Green Building XML) — spaces + areas/volumes from the IFC geometry, for OpenStudio /
    EnergyPlus / IES energy modelling. Simplified (building-level envelope, not per-space surfaces)."""
    from aec_data import gbxml  # type: ignore

    from ..models import Project
    p = db.get(Project, pid)
    xml = gbxml.to_gbxml_file(_source_ifc(db, pid), (p.name if p else None) or "Project")
    return Response(content=xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{safe_filename(p.name if p else "model", "model")}.gbxml"'})


@router.get("/projects/{pid}/exports/schedule.xlsx")
def export_schedule(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    from aec_data import schedule  # type: ignore

    acts = schedule.schedule_file(_source_ifc(db, pid))
    import json as _json

    rows = [{"id": a["id"], "name": a["name"], "start": a["start"], "finish": a["finish"],
             "element_count": len(a["guids"]), "guids": _json.dumps(a["guids"])} for a in acts]
    return _xlsx_response({"Schedule": _rows_to_sheet(rows)}, "schedule.xlsx")


_CLOSEOUT_MODULES = ("commissioning", "om_manual", "warranty", "as_built", "asset_register",
                     "completion_certificate", "punchlist")


@router.get("/projects/{pid}/closeout/package.zip")
def closeout_package(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
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
                _merged = _merge_sheets(cobie.cobie_file(p.source_ifc), _closeout_cobie_sheets(db, pid))
                _cobie = {k: _rows_to_sheet(v) for k, v in _merged.items()}
                z.writestr("data/cobie.xlsx", _xlsx_bytes(_cobie))
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
        # turnover: substantial-completion status + record model version
        try:
            from .. import turnover
            z.writestr("turnover/status.json", json.dumps(turnover.package_status(db, pid), indent=2, default=str))
        except Exception as e:                    # noqa: BLE001 — best-effort
            z.writestr("turnover/STATUS_ERROR.txt", str(e)[:300])
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe_filename(p.name)}_closeout.zip"'})
