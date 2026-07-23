"""Land/parcel screening endpoints — screen a parcel set + data-connector status."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from .. import parcels, parcels_bridge
from ..rbac import current_user

router = APIRouter()


@router.post("/parcels/screen")
def screen(parcels_in: list[dict] = Body(..., embed=True, alias="parcels"),
           criteria: dict | None = Body(default=None), _: str = Depends(current_user)):
    """Filter + rank a parcel set by size/zoning/flood/utilities, each with a max-buildable envelope +
    conceptual cost (screen → envelope → proforma). Body: {parcels:[...], criteria:{...}}."""
    return parcels.screen(parcels_in, criteria)


@router.get("/parcels/data-status")
def data_status(_: str = Depends(current_user)):
    """Whether a nationwide parcel/comps data provider is connected (else screening uses your parcels)."""
    return parcels_bridge.status()


@router.post("/parcels/analyze")
def analyze(body: dict = Body(...), _: str = Depends(current_user)):
    """PARCEL-IMPORT — cadastral parcel geometry ingest (upload-driven GeoJSON/WKT, no gov scraping) →
    area / perimeter / centroid / bbox, and — with `zoning` + `proposal` — FAR / lot-coverage / height
    compliance with per-axis slack. Body: `{geojson?|wkt?, parcel_id?, zoning?: {max_far, max_coverage,
    max_height_m}, proposal?: {gfa_m2, footprint_m2, height_m}}`. Bad boundary → 422."""
    from fastapi import HTTPException

    from .. import parcel_geometry as pg
    try:
        return pg.analyze(body.get("geojson"), body.get("wkt"), body.get("parcel_id"),
                          body.get("zoning"), body.get("proposal"))
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(422, f"could not parse the parcel boundary: {e}")
