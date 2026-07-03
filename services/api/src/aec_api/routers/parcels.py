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
