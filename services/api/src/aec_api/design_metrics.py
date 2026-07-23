"""DESIGN-METRICS + DAYLIGHT (R16 Tier-2, Finch + VergeSense) — the live design-validation numbers over the
model: **program efficiency** (floors · GFA · net floor area · net-to-gross · unit count · area by space
type) and a **deterministic daylight estimate** from the model's actual windows. Pure over an opened model,
so it can recompute on every edit and turn program + daylight into active constraints beside the geometry —
not ray-traced (that rides the energy/daylight job track), just an honest analytical first look.

The daylight estimate is the **average daylight factor (ADF)** from the CIBSE formula
``ADF = (W·θ·T·M) / (A·(1−R²))`` applied at the building scale: W = total glazed area (from the IFC's
windows), A ≈ a surface-area multiple of the net floor area, with typical constants (below). It's an
estimate — labelled as one — good enough to flag "under-glazed / over-glazed" before a real simulation.
"""
from __future__ import annotations

from typing import Any

# CIBSE average-daylight-factor constants (documented so the estimate is honest, not a black box):
_T = 0.68    # glazing visible transmittance (double glazing, clean)
_THETA = 0.5  # visible sky angle factor (unobstructed vertical window ≈ 0.5)
_M = 0.9     # maintenance factor
_R = 0.5     # area-weighted interior surface reflectance
_SURF = 4.5  # total interior surface area as a multiple of floor area (typical room)
# ADF% = WFR × k, where k = θ·T·M / ((1−R²)·_SURF) × 100
_ADF_K = _THETA * _T * _M / ((1 - _R * _R) * _SURF) * 100.0   # ≈ 9.07
_DEFAULT_EFF = 0.82   # assumed net-to-gross when the model carries no gross area
_UNIT_HINTS = ("unit", "apartment", "apt", "dwelling", "residential", "flat", "condo", "suite")


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _window_area(w, ue) -> float:
    """One window's glazed area — Qto_WindowBaseQuantities.Area, else OverallWidth×OverallHeight."""
    try:
        q = (ue.get_psets(w, qtos_only=True) or {}).get("Qto_WindowBaseQuantities") or {}
        a = _num(q.get("Area"))
        if a > 0:
            return a
    except Exception:                                # noqa: BLE001 — opaque qtos: fall through
        pass
    ow, oh = _num(getattr(w, "OverallWidth", None)), _num(getattr(w, "OverallHeight", None))
    return ow * oh


def daylight_band(adf_pct: float) -> str:
    """Standard average-daylight-factor adequacy bands."""
    if adf_pct >= 2.0:
        return "good"          # bright, daylit
    if adf_pct >= 1.0:
        return "fair"          # supplementary lighting often needed
    return "limited"           # under-glazed for daylight


def metrics(model) -> dict[str, Any]:
    """Program-efficiency + daylight metrics over the model → a flat dict ready for a design KPI panel."""
    from . import space_util as su

    try:
        import ifcopenshell.util.element as ue
    except Exception:                                # noqa: BLE001 — no ifcopenshell
        ue = None

    spaces = su._spaces_from_model(model)            # [{guid, name, type, area}] — net floor areas
    net_area = round(sum(_num(s.get("area")) for s in spaces), 1)
    space_count = len(spaces)

    # gross floor area: prefer the model's storey gross quantities, else net ÷ assumed efficiency
    gross_area = 0.0
    try:
        for st in model.by_type("IfcBuildingStorey"):
            if ue is not None:
                q = (ue.get_psets(st, qtos_only=True) or {}).get("Qto_BuildingStoreyBaseQuantities") or {}
                gross_area += _num(q.get("GrossFloorArea"))
    except Exception:                                # noqa: BLE001
        gross_area = 0.0
    gross_area = round(gross_area, 1) or (round(net_area / _DEFAULT_EFF, 1) if net_area else 0.0)

    try:
        floors = len(model.by_type("IfcBuildingStorey"))
    except Exception:                                # noqa: BLE001
        floors = 0

    # area rolled up by space type + unit count (residential-type spaces)
    by_type_agg: dict[str, float] = {}
    unit_count = 0
    for s in spaces:
        t = s.get("type") or "Unclassified"
        by_type_agg[t] = by_type_agg.get(t, 0.0) + _num(s.get("area"))
        if any(h in t.lower() for h in _UNIT_HINTS):
            unit_count += 1
    by_type = sorted(({"type": k, "area_m2": round(v, 1)} for k, v in by_type_agg.items()),
                     key=lambda r: -r["area_m2"])

    # daylight: total glazed area from the IFC's windows → window-to-floor ratio → ADF estimate
    win_area = 0.0
    win_count = 0
    if ue is not None:
        try:
            windows = model.by_type("IfcWindow")
        except Exception:                            # noqa: BLE001
            windows = []
        win_count = len(windows)
        for w in windows:
            win_area += _window_area(w, ue)
    win_area = round(win_area, 1)
    wfr = round(win_area / net_area, 4) if net_area else 0.0     # window-to-floor-area ratio
    adf_pct = round(wfr * _ADF_K, 2)

    net_to_gross = round(net_area / gross_area, 3) if gross_area else 0.0
    return {
        "floors": floors, "space_count": space_count,
        "net_floor_area_m2": net_area, "gross_floor_area_m2": gross_area,
        "net_to_gross": net_to_gross, "unit_count": unit_count,
        "avg_unit_m2": round(net_area / unit_count, 1) if unit_count else 0.0,
        "by_type": by_type,
        "daylight": {
            "window_count": win_count, "glazed_area_m2": win_area,
            "window_to_floor_ratio": wfr, "avg_daylight_factor_pct": adf_pct,
            "band": daylight_band(adf_pct),
            "estimate": True,
            "note": "Average daylight factor ESTIMATED from total glazed area vs net floor area (CIBSE "
                    "formula, typical constants — not a ray-traced simulation). Bands: ≥2% good · 1–2% "
                    "fair · <1% limited.",
        },
        "note": "Program-efficiency + daylight metrics computed over the model — recompute on each edit to "
                "keep GFA / net-to-gross / unit count / daylight as live design constraints.",
    }
