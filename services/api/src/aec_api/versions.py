"""Model version history + diff.

Snapshot the project's elements at each publish so two versions can be diffed. Beyond added/removed
elements, MODEL-DIFF stores a per-element **fingerprint** (class · type · level · name · Pset-hash ·
Qto-hash) so a GUID present in both revisions but *modified* — re-typed, re-leveled, renamed, resized
(quantity Δ), or re-propertied — is reported with *what* changed, not silently counted as unchanged.
GUID-stable authoring makes the diff real. (Pure rigid geometry moves are out of scope — geometry streams
as fragments, not this index; a resize shows up via its Qto delta.)
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import ModelVersion


def _guids(idx: dict) -> list[str]:
    return sorted({e["guid"] for e in (idx.get("elements") or []) if e.get("guid")})


def _h(obj: Any) -> str:
    """A short, stable hash of a JSON-able object (sorted keys), for Pset/Qto fingerprinting."""
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode("utf-8"),
                        usedforsecurity=False).hexdigest()[:12]


def _prop_hashes(psets: dict | None, qtos: dict | None) -> dict[str, str]:
    """Flat ``{"SetName.PropName": value_hash}`` over an element's Psets + Qtos — so a diff can name the
    exact properties/quantities that changed (not just 'properties changed'), without storing the values
    themselves (each is a short hash, so the version blob stays bounded)."""
    out: dict[str, str] = {}
    for group in (psets or {}, qtos or {}):
        for set_name, props in group.items():
            if not isinstance(props, dict):
                continue
            for prop, val in props.items():
                if prop == "id":                        # ifcopenshell stashes the pset entity id here
                    continue
                out[f"{set_name}.{prop}"] = _h(val)
    return out


def _fingerprints(idx: dict) -> dict[str, list]:
    """{guid: [name, ifc_class, type_name, storey, pset_hash, qto_hash, prop_hashes]} — the diffable
    signature of every element. Splitting Psets vs Qtos into separate hashes lets the diff say 'properties
    changed' vs 'quantities changed'; position [6] carries per-property hashes so the diff can name which
    keys changed. Older versions store only positions [0..5] and degrade gracefully."""
    fp: dict[str, list] = {}
    for e in (idx.get("elements") or []):
        g = e.get("guid")
        if not g:
            continue
        fp[g] = [e.get("name"), e.get("ifc_class"), e.get("type_name"), e.get("storey"),
                 _h(e.get("psets") or {}), _h(e.get("qtos") or {}),
                 _prop_hashes(e.get("psets"), e.get("qtos"))]
    return fp


# the fingerprint tuple positions → the human label for what changed at that position
_FIELD_LABELS = [(0, "renamed"), (1, "reclassified"), (2, "retyped"),
                 (3, "moved to another level"), (4, "properties changed"), (5, "quantities changed")]


def _changes(before: list, after: list) -> list[str]:
    """Which fingerprint fields differ between two versions of the same element → change labels."""
    return [label for i, label in _FIELD_LABELS if i < len(before) and i < len(after) and before[i] != after[i]]


def snapshot(pid: str, idx: dict, note: str | None = None) -> dict[str, Any]:
    """Record a new version from a freshly-built properties index. Opens its own session so it can
    be called from the background publish worker. Stores the GUID set + per-element fingerprints."""
    from .db import SessionLocal
    guids = _guids(idx)
    fps = _fingerprints(idx)
    with SessionLocal() as db:
        last = db.query(ModelVersion).filter(ModelVersion.project_id == pid) \
            .order_by(ModelVersion.version.desc()).first()
        prev = set(last.guids or []) if last else set()
        prev_fp = (last.fingerprints or {}) if last else {}
        cur = set(guids)
        added, removed = cur - prev, prev - cur
        # modified = common guids whose fingerprint changed (only when both versions carry fingerprints)
        modified = sum(1 for g in (cur & prev) if g in fps and g in prev_fp and fps[g] != prev_fp[g])
        # skip a true no-op republish (identical elements AND fingerprints) to keep history meaningful
        if last and not added and not removed and not modified and prev_fp:
            return {"version": last.version, "skipped": "no element change"}
        if note is None:
            note = (f"+{len(added)}/-{len(removed)}" + (f"/~{modified}" if modified else "")) if last else "initial"
        v = ModelVersion(project_id=pid, version=(last.version + 1 if last else 1),
                         element_count=len(guids), guids=guids, fingerprints=fps, note=note)
        db.add(v)
        db.commit()
        return {"version": v.version, "element_count": v.element_count,
                "added": len(added), "removed": len(removed), "modified": modified}


def history(db: Session, pid: str) -> list[dict]:
    rows = db.query(ModelVersion).filter(ModelVersion.project_id == pid) \
        .order_by(ModelVersion.version.desc()).all()
    return [{"version": r.version, "element_count": r.element_count, "note": r.note,
             "review_status": getattr(r, "review_status", None) or "draft",
             "reviewed_by": r.reviewed_by, "review_note": r.review_note,
             "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


# MODEL-PUBLISH (R18): the canonical review transitions — submit sends a draft for review, approve
# and reject resolve it. Anything else 409s. The model file pointer is never touched here.
_REVIEW_ACTIONS = {"submit": ("draft", "in_review"), "approve": ("in_review", "approved"),
                   "reject": ("in_review", "draft")}


def review(db: Session, pid: str, version: int, action: str, actor: str,
           note: str | None = None) -> dict:
    """Apply a review action to one version. Raises KeyError (unknown version) or ValueError
    (bad action / illegal transition — the caller maps to 404/409)."""
    r = db.query(ModelVersion).filter(ModelVersion.project_id == pid,
                                      ModelVersion.version == version).first()
    if r is None:
        raise KeyError(f"version {version} not found")
    tr = _REVIEW_ACTIONS.get(str(action or "").strip().lower())
    if tr is None:
        raise ValueError(f"action must be one of {', '.join(sorted(_REVIEW_ACTIONS))}")
    cur = getattr(r, "review_status", None) or "draft"
    if cur != tr[0]:
        raise ValueError(f"cannot {action} from {cur!r} (requires {tr[0]!r})")
    r.review_status = tr[1]
    r.reviewed_by = actor
    r.reviewed_at = datetime.now(timezone.utc)
    r.review_note = (str(note).strip()[:500] or None) if note else None
    db.commit()
    return {"version": r.version, "review_status": r.review_status, "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat(), "review_note": r.review_note}


def diff(db: Session, pid: str, a: int, b: int) -> dict[str, Any]:
    """Diff version `a` → `b`: added / removed / **modified** elements. Modified carries the change labels
    (renamed · reclassified · retyped · re-leveled · properties · quantities). Modified detection needs
    both versions to have fingerprints; older versions degrade to added/removed only (`modified_available`)."""
    def load(v: int) -> ModelVersion | None:
        return db.query(ModelVersion).filter(ModelVersion.project_id == pid,
                                             ModelVersion.version == v).first()
    ra, rb = load(a), load(b)
    sa = set(ra.guids or []) if ra else set()
    sb = set(rb.guids or []) if rb else set()
    fa = (ra.fingerprints or {}) if ra else {}
    fb = (rb.fingerprints or {}) if rb else {}
    added, removed = sorted(sb - sa), sorted(sa - sb)

    modified: list[dict] = []
    modified_available = bool(fa) and bool(fb)
    property_detail_available = False
    if modified_available:
        for g in (sa & sb):
            before, after = fa.get(g), fb.get(g)
            if not before or not after or before == after:
                continue
            changes = _changes(before, after)
            if not changes:
                continue
            entry = {"guid": g, "name": after[0], "ifc_class": after[1], "changes": changes}
            # position [6] carries per-property hashes → name exactly which keys changed (added/removed/edited)
            pb = before[6] if len(before) > 6 and isinstance(before[6], dict) else None
            pa = after[6] if len(after) > 6 and isinstance(after[6], dict) else None
            if pb is not None and pa is not None:
                property_detail_available = True
                keys = set(pb) | set(pa)
                diffs = [{"property": k,
                          "status": "added" if k not in pb else "removed" if k not in pa else "changed"}
                         for k in sorted(keys) if pb.get(k) != pa.get(k)]
                if diffs:
                    entry["changed_properties"] = diffs
            modified.append(entry)
        modified.sort(key=lambda m: (m["ifc_class"] or "", m["name"] or ""))

    return {"from": a, "to": b,
            "added": added, "removed": removed,
            "modified": modified, "modified_available": modified_available,
            "property_detail_available": property_detail_available,
            "added_count": len(added), "removed_count": len(removed),
            "modified_count": len(modified),
            "unchanged_count": len(sa & sb) - len(modified)}
