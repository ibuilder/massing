"""Parcel / comps data connector — OPTIONAL, a stub until a data provider is licensed.

Nationwide parcel + ownership + comps data (Acres' moat) is a licensing play — Regrid, ATTOM,
CoreLogic, Loveland — and conflicts with the offline/self-hosted ethos, so it's an opt-in connector
rather than owned infrastructure (same posture as the paid APS bridge in CLAUDE.md). OFF unless
`PARCEL_PROVIDER` is set; `fetch_parcels` raises an actionable error rather than returning fake data.
The screening engine (`parcels.screen`) works on parcels you already have (imported GeoJSON) without it."""
from __future__ import annotations

from . import settings_store


def provider() -> str:
    return (settings_store.get("PARCEL_PROVIDER") or "").strip()


def is_enabled() -> bool:
    return bool(provider())


def status() -> dict:
    if not is_enabled():
        return {"enabled": False, "provider": None,
                "message": "Parcel/comps data is not connected. Screening works on parcels you import "
                           "(GeoJSON) or enter; for nationwide parcel/ownership/comps data set "
                           "PARCEL_PROVIDER and wire a licensed provider (Regrid / ATTOM / CoreLogic). "
                           "This is a paid, online data feed — separate from the offline core."}
    return {"enabled": True, "provider": provider(),
            "message": f"Parcel data via '{provider()}'."}


def fetch_parcels(bbox: list[float] | None = None, owner: str | None = None) -> list[dict]:
    """Fetch parcels from the licensed provider — raises until one is wired (never fabricates data)."""
    if not is_enabled():
        raise RuntimeError("Parcel data is not connected (set PARCEL_PROVIDER and wire a licensed "
                           "provider). Massing screens parcels you supply; it does not ship parcel data.")
    raise NotImplementedError(
        f"Parcel fetch runs against the configured provider '{provider()}'. Implement the provider "
        "query in your deployment to enable nationwide parcel/ownership/comps data.")
