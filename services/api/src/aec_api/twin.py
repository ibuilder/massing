"""Digital-twin readiness + Digital Product Passport — the data a building needs to run as a twin.

A digital twin (ISO 23247 framework) needs every asset to have a persistent identity, a link to the
system it belongs to, and telemetry/sensor mapping points, with lifecycle data that stays usable across
phases. The EU Digital Product Passport (ESPR / revised CPR, phasing 2028-30) adds a globally unique
product identifier (GS1 Digital Link), environmental data (EPD) and manufacturer traceability. This
engine measures readiness from the asset register's new Digital Twin + Product Passport fields and the
building-system graph — deterministic, and honest about the DPP being an emerging requirement."""
from __future__ import annotations

from typing import Any

from . import modules as me

DPP_FIELDS = ("gs1_id", "epd_reference", "manufacturer_url")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def readiness(db, pid: str) -> dict[str, Any]:
    """Digital-twin + DPP readiness: asset↔system linkage, sensor mapping, product-passport
    completeness, and the building-system graph with its BMS-integration coverage."""
    assets = me.list_records(db, "asset_register", pid, limit=100000)
    systems = me.list_records(db, "building_system", pid, limit=10000)
    total = len(assets)
    linked = sum(1 for a in assets if (_d(a).get("system") or "").strip())
    sensored = sum(1 for a in assets if (_d(a).get("sensor_id") or "").strip())
    dpp_full = sum(1 for a in assets if all((_d(a).get(f) or "").strip() for f in DPP_FIELDS))
    dpp_any = sum(1 for a in assets if any((_d(a).get(f) or "").strip() for f in DPP_FIELDS))

    by_type: dict[str, int] = {}
    bms = 0
    for s in systems:
        d = _d(s)
        by_type[d.get("system_type") or "Other"] = by_type.get(d.get("system_type") or "Other", 0) + 1
        if (d.get("bms_integration") or "None") not in ("", "None"):
            bms += 1

    link_pct = _pct(linked, total)
    sensor_pct = _pct(sensored, total)
    dpp_pct = _pct(dpp_full, total)
    # twin readiness = the mean of the three asset-side signals that exist
    parts = [p for p in (link_pct, sensor_pct) if p is not None]
    twin_pct = round(sum(parts) / len(parts), 1) if parts else None
    return {
        "assets": total, "systems": len(systems), "systems_by_type": by_type,
        "system_linked_pct": link_pct, "sensor_mapped_pct": sensor_pct,
        "bms_integrated_systems": bms,
        "dpp": {"complete_pct": dpp_pct, "partial": dpp_any, "complete": dpp_full,
                "fields": list(DPP_FIELDS),
                "note": "Digital Product Passport is an emerging EU requirement (ESPR / revised CPR, "
                        "phasing 2028-30): GS1 product ID + EPD/environmental + manufacturer traceability."},
        "twin_readiness_pct": twin_pct,
        "note": "Twin readiness (ISO 23247): assets linked to a building system and mapped to a "
                "sensor/telemetry point, so live data can flow against a persistent asset identity.",
    }
