"""E8 — authoring guardrails: catch a broken edit BEFORE it's written, so a novice can't produce invalid
IFC (the reliability edge). This is the *pre-apply* complement to `model_qa` (which detects problems
after the fact). Rules are params-level and name-based, so they cover every recipe uniformly without a
per-recipe table: coordinates must be finite [E,N(,Z)] pairs, a line's endpoints must differ, physical
dimensions must be positive and finite, and enum params must be in range. Fast and deterministic (no I/O).

`precheck(recipe, params)` returns {ok, errors:[...], warnings:[...]}. Errors are things that would crash
the recipe or bake invalid geometry; warnings are suspicious-but-legal (e.g. an implausibly huge size that
usually means a unit mistake). The caller blocks on errors and may confirm-through warnings.
"""
from __future__ import annotations

import math
from typing import Any

# param-name conventions shared across the recipe registry
_POINT_PARAMS = {"start", "end", "point", "position"}
_POSITIVE_DIMS = {"height", "width", "depth", "thickness", "radius", "length", "diameter",
                  "ceiling_height", "panel_thickness", "mullion"}
_NONNEG_DIMS = {"sill"}                        # a sill/offset of 0 is legitimate
_HUGE_M = 5000.0                               # a single dimension this large is almost always a unit slip
_LOD_STAGES = {"100", "200", "300", "350", "400", "500"}
_PHASES = {"new", "existing", "demolish", "temporary"}


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _as_point(v: Any) -> list[float] | None:
    if not isinstance(v, (list, tuple)) or not (2 <= len(v) <= 3):
        return None
    if not all(_finite(c) for c in v):
        return None
    return [float(c) for c in v]


def precheck(recipe: str, params: dict | None) -> dict[str, Any]:
    """Validate an edit's params. Returns {ok, errors, warnings}. `params` values follow the registry's
    naming (start/end/point coordinates in [E,N] metres, positive physical dimensions, LOD stage/phase
    enums). Unknown recipes are not judged here (apply_recipe already rejects those)."""
    p = params or {}
    errors: list[str] = []
    warnings: list[str] = []

    # coordinates: finite [E,N(,Z)] pairs
    pts: dict[str, list[float]] = {}
    for name in _POINT_PARAMS:
        if name in p and p[name] is not None:
            pt = _as_point(p[name])
            if pt is None:
                errors.append(f"{name} must be a finite [E, N] point in metres")
            else:
                pts[name] = pt

    # a line's endpoints must differ (coincident start/end → a zero-length wall/beam, which crashes the
    # placement math with an opaque error)
    if "start" in pts and "end" in pts and math.dist(pts["start"][:2], pts["end"][:2]) < 1e-6:
        errors.append("start and end are the same point — the element would have zero length")

    # physical dimensions: finite and positive (sill may be zero)
    for name in _POSITIVE_DIMS:
        if name in p and p[name] is not None:
            if not _finite(p[name]):
                errors.append(f"{name} must be a finite number")
            elif float(p[name]) <= 0:
                errors.append(f"{name} must be greater than 0")
            elif float(p[name]) > _HUGE_M:
                warnings.append(f"{name} is {float(p[name]):g} m — unusually large; check the units")
    for name in _NONNEG_DIMS:
        if name in p and p[name] is not None:
            if not _finite(p[name]):
                errors.append(f"{name} must be a finite number")
            elif float(p[name]) < 0:
                errors.append(f"{name} must be 0 or greater")

    # integer counts must be >= 1
    for name in ("cols", "rows", "rooms_per_storey", "nx", "ny"):
        if name in p and p[name] is not None:
            try:
                if int(p[name]) < 1:
                    errors.append(f"{name} must be at least 1")
            except (TypeError, ValueError):
                errors.append(f"{name} must be a whole number")

    # enum params
    if recipe == "set_lod" and "stage" in p and str(p["stage"]) not in _LOD_STAGES:
        errors.append(f"LOD stage must be one of {sorted(_LOD_STAGES)}")
    if recipe == "set_phase" and "phase" in p and p.get("phase"):
        if str(p["phase"]).strip().lower() not in _PHASES:
            warnings.append(f"phase '{p['phase']}' isn't a standard status ({sorted(_PHASES)}); it'll be tagged verbatim")

    # required references present (params-level only — existence-in-model is checked at apply time)
    for name in ("host_guid", "guid"):
        if recipe in _NEEDS.get(name, ()) and not str(p.get(name) or "").strip():
            errors.append(f"{name} is required — select a host/target element first")
    if recipe in _NEEDS.get("guids", ()) and not (p.get("guids") or []):
        errors.append("no target elements — make a selection first")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# which recipes require which reference params (drives the "select something first" guard)
_NEEDS = {
    "host_guid": ("add_door", "add_window", "add_opening"),
    "guid": ("delete_element", "move_element", "rotate_element", "copy_element", "set_element_pset",
             "set_classification", "set_storey_elevation", "rename_storey"),
    "guids": ("set_lod", "set_phase", "verify_asbuilt"),   # map_properties works over all elements (rules), no selection
}
