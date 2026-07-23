"""Municipal permit open data — interchangeable multi-city feed, wired into the GC permit module.

- GET  /opendata/permit-cities                         the selectable cities
- GET  /projects/{pid}/opendata/permits                query a city (near a point / text)
- GET  /projects/{pid}/opendata/permits.geojson        same, as a GIS overlay layer
- POST /projects/{pid}/opendata/permits/import         create `permit` module records (dedup), GC side
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import modules as mod_engine
from .. import opendata, rbac
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.post("/projects/{pid}/permits/timeline")
def permits_timeline(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                     _: str = Depends(require_role("viewer"))):
    """PERMIT-TIMELINE — days-to-issue analytics (p25 / median / p75 by jurisdiction × type × valuation band)
    + a seasonal profile over the cached permit records, and — with a `target` — the pro-forma estimate
    (median = expected entitlement duration, p75 = the conservative carry). Body: `{permits?, target?:
    {jurisdiction, type, valuation}}`; falls back to the project's `permit` records when `permits` is omitted.
    409 without any permit data."""
    from fastapi import HTTPException

    from .. import permit_timeline as pt
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    permits = body.get("permits")
    if not permits:
        recs = mod_engine.list_records(db, "permit", pid, limit=1_000_000) if "permit" in mod_engine.TABLES else []
        permits = []
        for r in recs:
            d = r.get("data") or {}
            permits.append({**d, "filed": d.get("applied_date") or d.get("filed_date") or d.get("application_date"),
                            "type": d.get("permit_type"),
                            "jurisdiction": d.get("source_city") or d.get("authority"),
                            "valuation": d.get("est_cost")})
    if not permits:
        raise HTTPException(409, "no permit data — supply `permits` or import permits into the project first")
    return pt.analyze(permits, body.get("target"))


@router.get("/opendata/permit-cities")
def permit_cities(_: str = Depends(rbac.current_user)):
    """Cities whose building-permit open data we can read, and whether radius search is supported."""
    return {"cities": opendata.list_cities()}


def _query(city: str, lat, lon, radius, address, q, limit):
    if not city:
        raise HTTPException(422, "city is required")
    try:
        return opendata.fetch_permits(city, lat=lat, lon=lon, radius_m=radius or 1500,
                                      address=address, q=q, limit=limit)
    except opendata.OpendataError as e:
        raise HTTPException(502, str(e)) from e


@router.get("/projects/{pid}/opendata/permits")
def query_permits(pid: str, city: str, lat: float | None = None, lon: float | None = None,
                  radius: float | None = None, address: str | None = None, q: str | None = None,
                  limit: int = 100, _: str = Depends(require_role("viewer"))):
    """Nearby / matching municipal filings — owner, architect, GC, units, cost, status — for
    acquisition intel and to seed the project's own permit log."""
    recs = _query(city, lat, lon, radius, address, q, limit)
    return {"city": city, "count": len(recs), "permits": recs}


@router.get("/projects/{pid}/opendata/permits.geojson")
def permits_geojson(pid: str, city: str, lat: float | None = None, lon: float | None = None,
                    radius: float | None = None, address: str | None = None, q: str | None = None,
                    limit: int = 200, _: str = Depends(require_role("viewer"))):
    """The same filings as a GeoJSON FeatureCollection for the viewer's GIS overlay (points only)."""
    recs = _query(city, lat, lon, radius, address, q, limit)
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {k: r[k] for k in ("permit_number", "permit_type", "status", "address",
                                         "owner", "applicant", "contractor", "units", "est_cost",
                                         "issued_date", "description")},
    } for r in recs if r.get("lat") is not None and r.get("lon") is not None]
    return {"type": "FeatureCollection", "features": feats}


# city permit_type / status vocabularies -> the permit module's select options
def _map_type(t: str | None) -> str:
    s = (t or "").lower()
    for needle, val in (("demolition", "Demolition"), ("demo", "Demolition"), ("foundation", "Foundation"),
                        ("electrical", "Electrical"), ("plumb", "Plumbing"), ("hvac", "Mechanical / HVAC"),
                        ("mechanical", "Mechanical / HVAC"), ("elevator", "Elevator"),
                        ("grad", "Grading / Sitework"), ("site", "Grading / Sitework"),
                        ("occupancy", "Certificate of Occupancy"), ("fire", "Fire / Life-Safety")):
        if needle in s:
            return val
    return "Building"


def _map_status(s: str | None) -> str:
    t = (s or "").lower()
    if any(k in t for k in ("issue", "approved", "permit entire")):
        return "Issued"
    if "expire" in t:
        return "Expired"
    if any(k in t for k in ("close", "complete", "final", "signed off", "cofo")):
        return "Closed"
    if any(k in t for k in ("review", "pending", "progress", "in process", "filed", "intake")):
        return "Under Review"
    return "Applied"


def _expires(rec: dict) -> str:
    if rec.get("expires_date"):
        return rec["expires_date"]
    base = rec.get("issued_date") or rec.get("filed_date")
    try:
        d = date.fromisoformat(str(base)[:10]) if base else date.today()
    except ValueError:
        d = date.today()
    return (d + timedelta(days=365)).isoformat()        # AHJ permits typically run ~1yr; editable


@router.post("/projects/{pid}/opendata/permits/import")
def import_permits(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                   user: str = Depends(require_role("editor"))):
    """Pull a city's filings for the site and create `permit` records on the GC side, source-tagged so
    they don't duplicate on re-import. Body: {city, lat?, lon?, radius?, address?, q?, max?}."""
    city = (body or {}).get("city")
    recs = _query(city, body.get("lat"), body.get("lon"), body.get("radius"),
                  body.get("address"), body.get("q"), int(body.get("max") or 50))
    party = rbac.party_role_for(db, pid, user)
    existing = {(str((r.get("data") or {}).get("number") or "").strip(),
                str((r.get("data") or {}).get("source_city") or ""))
               for r in mod_engine.list_records(db, "permit", pid, limit=1_000_000)}
    imported, skipped, refs = 0, 0, []
    for r in recs:
        num = (r.get("permit_number") or "").strip()
        if not num or (num, city) in existing:
            skipped += 1
            continue
        data = {
            "name": (r.get("description") or f"{r.get('permit_type') or 'Permit'} {num}")[:120],
            "permit_type": _map_type(r.get("permit_type")),
            "authority": r.get("authority"),
            "number": num,
            "status": _map_status(r.get("status")),
            "issued_date": r.get("issued_date"),
            "expires": _expires(r),
            "fee": r.get("fee"),
            # provenance + the richer open-data fields (kept so nothing is lost; round-trips on re-import)
            "source": "opendata", "source_city": city, "source_url": r.get("url"),
            "source_status": r.get("status"), "address": r.get("address"),
            "owner": r.get("owner"), "applicant": r.get("applicant"), "contractor": r.get("contractor"),
            "units": r.get("units"), "floor_area": r.get("floor_area"), "est_cost": r.get("est_cost"),
            "lat": r.get("lat"), "lon": r.get("lon"),
        }
        rec = mod_engine.create_record(db, "permit", pid, {"data": data}, user, party)
        existing.add((num, city))
        imported += 1
        refs.append(rec.get("ref"))
    return {"imported": imported, "skipped": skipped, "found": len(recs), "refs": refs}
