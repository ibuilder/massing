"""Model version history + diff — snapshot the project's element GUID set at each publish so two
versions can be diffed (added / removed elements). GUID-stable authoring makes the diff real."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import ModelVersion


def _guids(idx: dict) -> list[str]:
    return sorted({e["guid"] for e in (idx.get("elements") or []) if e.get("guid")})


def snapshot(pid: str, idx: dict, note: str | None = None) -> dict[str, Any]:
    """Record a new version from a freshly-built properties index. Opens its own session so it can
    be called from the background publish worker."""
    from .db import SessionLocal
    guids = _guids(idx)
    with SessionLocal() as db:
        last = db.query(ModelVersion).filter(ModelVersion.project_id == pid) \
            .order_by(ModelVersion.version.desc()).first()
        prev = set(last.guids or []) if last else set()
        cur = set(guids)
        # skip a no-op republish (identical element set) to keep history meaningful
        if last and prev == cur:
            return {"version": last.version, "skipped": "no element change"}
        v = ModelVersion(project_id=pid, version=(last.version + 1 if last else 1),
                         element_count=len(guids), guids=guids,
                         note=note or (f"+{len(cur - prev)}/-{len(prev - cur)}" if last else "initial"))
        db.add(v)
        db.commit()
        return {"version": v.version, "element_count": v.element_count,
                "added": len(cur - prev), "removed": len(prev - cur)}


def history(db: Session, pid: str) -> list[dict]:
    rows = db.query(ModelVersion).filter(ModelVersion.project_id == pid) \
        .order_by(ModelVersion.version.desc()).all()
    return [{"version": r.version, "element_count": r.element_count, "note": r.note,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


def diff(db: Session, pid: str, a: int, b: int) -> dict[str, Any]:
    def load(v: int) -> set[str]:
        row = db.query(ModelVersion).filter(ModelVersion.project_id == pid,
                                            ModelVersion.version == v).first()
        return set(row.guids or []) if row else set()
    sa, sb = load(a), load(b)
    added, removed = sorted(sb - sa), sorted(sa - sb)
    return {"from": a, "to": b, "added": added, "removed": removed,
            "added_count": len(added), "removed_count": len(removed),
            "unchanged_count": len(sa & sb)}
