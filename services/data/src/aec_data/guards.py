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

    # sloped-wall top heights (set_wall_slope): finite and >= 0 (a 0 m end is legitimate)
    for name in ("start_height", "end_height"):
        if name in p and p[name] is not None:
            if not _finite(p[name]):
                errors.append(f"{name} must be a finite number")
            elif float(p[name]) < 0:
                errors.append(f"{name} must be 0 or greater")

    # nested type `dims` map (create_type / edit_type) — every value finite; a *dimension* key (width/
    # height/…) must be positive, like the top-level params (non-dimension keys are only finite-checked).
    dims = p.get("dims")
    if isinstance(dims, dict):
        for k, v in dims.items():
            if v is None:
                continue
            if not _finite(v):
                errors.append(f"dims.{k} must be a finite number")
            elif k in _POSITIVE_DIMS and float(v) <= 0:
                errors.append(f"dims.{k} must be greater than 0")
            elif k in _NONNEG_DIMS and float(v) < 0:
                errors.append(f"dims.{k} must be 0 or greater")
            elif abs(float(v)) > _HUGE_M:
                warnings.append(f"dims.{k} is {float(v):g} — unusually large; check the units")

    # a polyline / footprint `points` array: each vertex a finite [E, N(,Z)] pair
    pl = p.get("points")
    if isinstance(pl, (list, tuple)) and pl:
        if any(_as_point(pt) is None for pt in pl):
            errors.append("points must all be finite [E, N] pairs in metres")
        elif len(pl) < 2:
            errors.append("points needs at least 2 vertices")

    # a procedural mesh (add_mesh_representation): verts + faces must be non-empty lists
    if recipe == "add_mesh_representation":
        if not isinstance(p.get("verts"), (list, tuple)) or not p.get("verts"):
            errors.append("verts must be a non-empty list of [x, y, z] points")
        if not isinstance(p.get("faces"), (list, tuple)) or not p.get("faces"):
            errors.append("faces must be a non-empty list of [i, j, k] indices")

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
    for name, msg in _REF_MSG.items():
        if recipe in _NEEDS.get(name, ()) and not str(p.get(name) or "").strip():
            errors.append(f"{name} is required — {msg}")
    if recipe in _NEEDS.get("guids", ()) and not (p.get("guids") or []):
        errors.append("no target elements — make a selection first")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


# single-reference param -> the friendly "why" shown when it's missing
_REF_MSG = {
    "host_guid": "select a host element first",
    "guid": "select a target element first",
    "guid_a": "pick the first element to connect",
    "guid_b": "pick the second element to connect",
    "system": "a system name is required",
}

# which recipes require which reference params (drives the "select something first" guard)
_NEEDS = {
    "host_guid": ("add_door", "add_window", "add_opening"),
    "guid": ("delete_element", "move_element", "rotate_element", "copy_element", "set_element_pset",
             "set_classification", "set_storey_elevation", "rename_storey", "set_wall_slope"),
    "guid_a": ("connect_mep", "connect_elements"),
    "guid_b": ("connect_mep", "connect_elements"),
    "system": ("set_system_predefined",),
    "guids": ("set_lod", "set_phase", "verify_asbuilt", "set_manufacturer_info", "record_asbuilt_dimension",
              "attach_document", "attach_om_document", "set_spec_link"),   # map_properties works over all elements (rules), no selection
}


# ── E8: model-aware guardrails — checks that need the OPEN model at precheck time ──────────────────
# The pure `precheck` validates shapes; this layer validates REFERENCES against reality: the host of
# a door/window is actually a wall, a named storey exists, a GUID being edited resolves, an MEP
# connect targets elements that have ports. Runs inside apply_recipe/apply_recipes AFTER the model
# opens and BEFORE any mutation — so a hallucinated GUID or a typo'd storey never half-applies.

_HOSTABLE = ("IfcWall", "IfcWallStandardCase", "IfcCurtainWall")


def _safe_guid(model, guid):
    try:
        return model.by_guid(guid)
    except Exception:  # noqa: BLE001 — malformed GUID → unresolved
        return None


def model_precheck(model, recipe: str, params: dict | None) -> dict[str, Any]:
    """Validate an edit's references against the open model. Returns {ok, errors, warnings} in the
    same shape as `precheck`. Only judges what it can see — unknown params pass through."""
    p = params or {}
    errors: list[str] = []
    warnings: list[str] = []

    # a named storey must exist (recipes fall back to the first storey when None — that's fine)
    storey = p.get("storey")
    if storey:
        names = [s.Name for s in model.by_type("IfcBuildingStorey")]
        if storey not in names:
            errors.append(f"storey {storey!r} not found — have {names}")

    # door/window/opening hosts must resolve AND be a wall
    if recipe in _NEEDS["host_guid"] and p.get("host_guid"):
        host = _safe_guid(model, p["host_guid"])
        if host is None:
            errors.append(f"host {p['host_guid']} not found in the model")
        elif host.is_a() not in _HOSTABLE:
            errors.append(f"host {p['host_guid']} is a {host.is_a()} — a door/window/opening needs a wall")

    # single-element edits: the GUID must resolve
    if recipe in _NEEDS["guid"] and p.get("guid") and _safe_guid(model, p["guid"]) is None:
        errors.append(f"element {p['guid']} not found in the model")

    # port-to-port connects: both ends must resolve and carry at least one port
    if recipe == "connect_mep":
        from . import mep
        for k in ("guid_a", "guid_b"):
            el = _safe_guid(model, p.get(k)) if p.get(k) else None
            if el is None:
                errors.append(f"{k} {p.get(k)!r} not found in the model")
            elif not mep._ports(el):
                errors.append(f"{k} {p.get(k)} ({el.is_a()}) has no connection ports")

    # batch tags: warn (not fail) when most of the GUIDs don't resolve — one stale GUID is normal,
    # a fully-unresolvable list means the selection came from a different model
    guids = p.get("guids")
    if recipe in _NEEDS["guids"] and isinstance(guids, list) and guids:
        missing = sum(1 for g in guids if _safe_guid(model, g) is None)
        if missing == len(guids):
            errors.append(f"none of the {len(guids)} element(s) exist in this model — "
                          "the selection came from a different model/version")
        elif missing:
            warnings.append(f"{missing} of {len(guids)} element(s) not found — they'll be skipped")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
