"""Envelope code-compliance (D3): check wall / roof / floor / fenestration assemblies against the
IECC 2021 prescriptive envelope minimums for their climate zone.

Opaque assemblies (wall/roof/floor/slab) are checked against a minimum R-value; fenestration
(window/door/skylight) against a maximum U-factor. When only the complementary property is given, R and
U are treated as reciprocals (a first-pass; assembly R ≠ 1/U exactly, but close enough to flag). The
minimums below are representative of the IECC 2021 commercial prescriptive tables (C402.1.3 / C402.4) —
a starting compliance screen, not a stamped energy model.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me

# Minimum opaque R-value by IECC climate zone (1–8). Representative IECC 2021 prescriptive values.
_MIN_R = {
    "Wall": {1: 13, 2: 13, 3: 17, 4: 20, 5: 20, 6: 20, 7: 29, 8: 29},
    "Roof": {1: 25, 2: 25, 3: 25, 4: 30, 5: 30, 6: 30, 7: 35, 8: 35},
    "Floor": {1: 0, 2: 13, 3: 19, 4: 30, 5: 30, 6: 30, 7: 38, 8: 38},
    "Slab-on-grade": {1: 0, 2: 0, 3: 0, 4: 10, 5: 10, 6: 10, 7: 15, 8: 15},
}
# Maximum fenestration U-factor by climate zone.
_MAX_U = {
    "Window": {1: 0.50, 2: 0.50, 3: 0.46, 4: 0.38, 5: 0.38, 6: 0.36, 7: 0.29, 8: 0.29},
    "Door": {1: 0.50, 2: 0.50, 3: 0.46, 4: 0.38, 5: 0.38, 6: 0.36, 7: 0.29, 8: 0.29},
    "Skylight": {1: 0.75, 2: 0.65, 3: 0.55, 4: 0.50, 5: 0.50, 6: 0.50, 7: 0.50, 8: 0.50},
}
_OPAQUE = set(_MIN_R)
_FENESTRATION = set(_MAX_U)


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _zone(v: Any) -> int | None:
    try:
        z = int(str(v)[0])
        return z if 1 <= z <= 8 else None
    except (TypeError, ValueError):
        return None


def check_assembly(element_type: str, climate_zone: Any, r_value: float | None = None,
                   u_factor: float | None = None) -> dict[str, Any]:
    """Check one assembly. Opaque → R ≥ min; fenestration → U ≤ max. R/U treated as reciprocals."""
    z = _zone(climate_zone)
    r_value, u_factor = _num(r_value), _num(u_factor)
    out: dict[str, Any] = {"element_type": element_type, "climate_zone": z,
                           "r_value": r_value, "u_factor": u_factor, "compliant": None}
    if z is None:
        out["issue"] = "no valid climate zone (1–8)"
        return out
    if element_type in _OPAQUE:
        provided_r = r_value if r_value is not None else (1 / u_factor if u_factor else None)
        required = _MIN_R[element_type][z]
        out.update({"required_min_r": required, "provided_r": round(provided_r, 1) if provided_r else None})
        if provided_r is None:
            out["issue"] = "no R-value or U-factor given"
        else:
            out["compliant"] = provided_r >= required
            out["margin"] = round(provided_r - required, 1)
    elif element_type in _FENESTRATION:
        provided_u = u_factor if u_factor is not None else (1 / r_value if r_value else None)
        required = _MAX_U[element_type][z]
        out.update({"required_max_u": required, "provided_u": round(provided_u, 3) if provided_u else None})
        if provided_u is None:
            out["issue"] = "no U-factor or R-value given"
        else:
            out["compliant"] = provided_u <= required
            out["margin"] = round(required - provided_u, 3)
    else:
        out["issue"] = f"unknown element type '{element_type}'"
    return out


def _d(r: dict) -> dict:
    return r.get("data") or r


def audit(db: Session, pid: str) -> dict[str, Any]:
    """Check every envelope_assembly record against IECC 2021 minimums; roll up compliance."""
    rows = me.list_records(db, "envelope_assembly", pid, limit=100000) \
        if "envelope_assembly" in me.TABLES else []
    results = []
    checked = compliant = 0
    for r in rows:
        d = _d(r)
        res = check_assembly(d.get("element_type", ""), d.get("climate_zone"),
                             d.get("r_value"), d.get("u_factor"))
        res["name"] = d.get("name", "")
        results.append(res)
        if res["compliant"] is not None:
            checked += 1
            compliant += 1 if res["compliant"] else 0
    return {
        "total": len(rows), "checked": checked, "compliant": compliant,
        "compliance_pct": round(100 * compliant / checked, 1) if checked else None,
        "results": results,
        "note": "Opaque assemblies vs IECC 2021 minimum R; fenestration vs maximum U, by climate zone. "
                "Representative prescriptive values — a first-pass screen, not a stamped energy model.",
    }
