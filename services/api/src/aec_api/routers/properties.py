"""Serves the Phase 1 properties index (geometry stays in .frag, data comes from here).
Selection in the viewer raycasts to a GUID, then fetches Psets from these endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, UploadFile, File

from .. import storage

router = APIRouter()

# project_id -> { guid -> element record }  (loaded from uploaded props.json)
_INDEX: dict[str, dict[str, dict]] = {}
_META: dict[str, dict] = {}


def _load(pid: str, payload: dict) -> int:
    _META[pid] = {k: payload.get(k) for k in ("schema", "project", "counts", "facets")}
    _INDEX[pid] = {e["guid"]: e for e in payload.get("elements", [])}
    return len(_INDEX[pid])


@router.post("/projects/{pid}/properties/index")
async def upload_index(pid: str, file: UploadFile = File(...)):
    """Upload the props.json produced by the data service (`aec_data.cli index`)."""
    payload = json.loads(await file.read())
    storage.put(f"{pid}/props.json", json.dumps(payload).encode("utf-8"))
    n = _load(pid, payload)
    return {"loaded": n, "meta": _META[pid]}


def _ensure_loaded(pid: str) -> None:
    if pid in _INDEX:
        return
    key = f"{pid}/props.json"
    if storage.exists(key):
        _load(pid, json.loads(storage.get(key)))


@router.get("/projects/{pid}/properties/meta")
def meta(pid: str):
    _ensure_loaded(pid)
    if pid not in _META:
        raise HTTPException(404, "no properties index for project")
    return _META[pid]


@router.get("/projects/{pid}/elements")
def list_elements(pid: str, ifc_class: str | None = None, storey: str | None = None, limit: int = 500):
    _ensure_loaded(pid)
    if pid not in _INDEX:
        raise HTTPException(404, "no properties index for project")
    out = []
    for e in _INDEX[pid].values():
        if ifc_class and e["ifc_class"] != ifc_class:
            continue
        if storey and e["storey"] != storey:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


@router.get("/projects/{pid}/elements/{guid}")
def element(pid: str, guid: str):
    _ensure_loaded(pid)
    rec = _INDEX.get(pid, {}).get(guid)
    if not rec:
        raise HTTPException(404, "element not found")
    return rec
