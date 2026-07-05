"""Field verification & install-coverage — mark model elements installed/verified against design,
log deviations (photo-anchored), and report % coverage for the verified-handover to operations
(Argyle-style spatial QA, without AR hardware). Keyed by IFC GlobalId so it survives re-conversion."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..db import get_db
from ..models import ElementVerification
from ..rbac import require_role
from .properties import _INDEX, _ensure_loaded

router = APIRouter()

STATUSES = ("pending", "installed", "verified", "deviation")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public(v: ElementVerification) -> dict:
    return {"guid": v.guid, "ifc_class": v.ifc_class, "storey": v.storey, "status": v.status,
            "note": v.note, "has_photo": bool(v.photo_key), "verified_by": v.verified_by,
            "modified_at": v.modified_at.isoformat() if v.modified_at else None}


@router.get("/projects/{pid}/verification")
def list_verifications(pid: str, status: str | None = None, db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    stmt = select(ElementVerification).where(ElementVerification.project_id == pid)
    if status:
        stmt = stmt.where(ElementVerification.status == status)
    return [_public(v) for v in db.execute(stmt).scalars()]


@router.get("/projects/{pid}/verification/coverage")
def coverage(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Install-coverage summary: of the model's elements, how many are installed/verified, plus the
    deviation count. `total` comes from the uploaded property index (0 if none yet)."""
    _ensure_loaded(pid)
    total = len(_INDEX.get(pid, {}))
    by_status = dict.fromkeys(STATUSES, 0)
    rows = list(db.execute(select(ElementVerification.status, ElementVerification.guid)
                           .where(ElementVerification.project_id == pid)).all())
    tracked_guids = set()
    for st, guid in rows:
        by_status[st] = by_status.get(st, 0) + 1
        tracked_guids.add(guid)
    # untracked elements count as pending against the model total
    tracked = len(tracked_guids)
    by_status["pending"] = max(by_status.get("pending", 0), (total - tracked) if total else by_status.get("pending", 0))
    verified = by_status.get("verified", 0)
    installed = verified + by_status.get("installed", 0)
    denom = total or tracked or 1
    return {
        "total_elements": total,
        "tracked": tracked,
        "by_status": by_status,
        "verified": verified,
        "installed": installed,
        "deviations": by_status.get("deviation", 0),
        "verified_pct": round(100 * verified / denom, 1),
        "installed_pct": round(100 * installed / denom, 1),
    }


@router.get("/projects/{pid}/verification/deviations")
def deviations(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The deviation log — elements flagged as not matching design (for the punch / ops handover)."""
    stmt = (select(ElementVerification)
            .where(ElementVerification.project_id == pid, ElementVerification.status == "deviation")
            .order_by(ElementVerification.modified_at.desc()))
    return [_public(v) for v in db.execute(stmt).scalars()]


@router.put("/projects/{pid}/verification/{guid}")
def set_status(pid: str, guid: str, body: dict = Body(...), db: Session = Depends(get_db),
               user: str = Depends(require_role("editor"))):
    """Set an element's field-verification status (installed / verified / deviation / pending).
    Upserts by (project, guid); stamps ifc_class/storey from the property index when available."""
    status = (body.get("status") or "").strip()
    if status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}")
    _ensure_loaded(pid)
    el = _INDEX.get(pid, {}).get(guid) or {}
    v = db.execute(select(ElementVerification).where(
        ElementVerification.project_id == pid, ElementVerification.guid == guid)).scalar_one_or_none()
    if v is None:
        v = ElementVerification(project_id=pid, guid=guid)
        db.add(v)
    v.status = status
    if "note" in body:
        v.note = body.get("note")
    v.ifc_class = el.get("ifc_class") or v.ifc_class
    v.storey = el.get("storey") or v.storey
    v.verified_by = user
    v.modified_at = _now()
    db.commit()
    return _public(v)


@router.post("/projects/{pid}/verification/{guid}/photo")
async def upload_photo(pid: str, guid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: str = Depends(require_role("editor"))):
    """Attach a field photo to an element's verification (deviation evidence / install proof)."""
    import os
    import re
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(file.filename or "photo")).lstrip(".") or "photo"
    key = f"verification/{pid}/{guid}/{safe}"
    storage.put(key, await file.read())
    v = db.execute(select(ElementVerification).where(
        ElementVerification.project_id == pid, ElementVerification.guid == guid)).scalar_one_or_none()
    if v is None:
        v = ElementVerification(project_id=pid, guid=guid, status="installed", verified_by=user)
        db.add(v)
    v.photo_key = key
    v.modified_at = _now()
    db.commit()
    return {"guid": guid, "has_photo": True}
