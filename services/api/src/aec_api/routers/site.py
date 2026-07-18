"""SITE-1 router — the project's open-geodata site context (OSM buildings/roads/landuse).

Fetch-once, offline-after: the first call (opt-in, needs network) queries Overpass and caches the
GeoJSON in object storage; every later call serves the cache so the viewer stays offline-capable.
`refresh=true` re-fetches. Coordinates come from query params when given, else from the source IFC's
site georeferencing (IfcSite.RefLatitude/RefLongitude)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import storage
from ..db import get_db
from ..deps import open_source_ifc
from ..rbac import require_role

router = APIRouter()


def _cache_key(pid: str) -> str:
    return f"{pid}/site/context.json"


@router.get("/projects/{pid}/site-context")
async def site_context(pid: str, lat: float | None = Query(None), lon: float | None = Query(None),
                       radius: float = Query(300.0, ge=50, le=2000),
                       refresh: bool = Query(False),
                       db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """OSM site context around the project — building footprints (height/levels), roads, land-use —
    as GeoJSON for the viewer's reference layer. Cached after the first fetch (offline afterwards);
    `refresh=true` re-queries. ODbL attribution ships in the payload. 409 when no coordinates are
    available (pass lat/lon, or georeference the model's IfcSite)."""
    from .. import site_context as sc

    key = _cache_key(pid)
    if not refresh and storage.exists(key):
        return json.loads(storage.get(key))

    if lat is None or lon is None:
        try:
            model = await run_in_threadpool(open_source_ifc, db, pid)
            ll = sc.site_lat_lon(model)
        except HTTPException:
            ll = None
        if not ll:
            raise HTTPException(409, "no site coordinates — pass ?lat=&lon= or georeference the "
                                     "model's IfcSite (RefLatitude/RefLongitude)")
        lat, lon = ll

    try:
        out = await run_in_threadpool(sc.fetch, lat, lon, radius)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    out["fetched_at"] = datetime.now(timezone.utc).isoformat()
    out["cached"] = True
    storage.put(key, json.dumps(out).encode())
    return out


@router.delete("/projects/{pid}/site-context")
def clear_site_context(pid: str, _sec: str = Depends(require_role("editor"))):
    """Drop the cached site context (next GET re-fetches)."""
    key = _cache_key(pid)
    existed = storage.exists(key)
    if existed:
        storage.delete(key)
    return {"deleted": existed}
