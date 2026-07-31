"""Phase 5 — Quantity takeoff (QTO) → estimating (5D).

Pull base quantities from IfcElementQuantity/Psets; fall back to geometry-derived
length/area/volume when quantities are missing. Map elements to cost codes (CSI
MasterFormat / UniFormat) via a user-editable table; multiply by unit cost → 5D."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name

try:
    import ifcopenshell.geom as _geom
    import ifcopenshell.util.shape as _shape
    import numpy as _np
    _GEOM_OK = True
except Exception:  # pragma: no cover - geom backend optional
    _GEOM_OK = False

# common base-quantity keys across IFC qto psets
_QTY_KEYS = {
    "length": ("Length", "NetLength", "GrossLength"),
    "area": ("NetArea", "GrossArea", "Area", "NetSideArea", "GrossSideArea"),
    "volume": ("NetVolume", "GrossVolume", "Volume"),
    "weight": ("NetWeight", "GrossWeight", "Weight"),
}


@dataclass
class CostCodeRow:
    """One line of the editable mapping table (CSV-backed in production)."""
    match_class: str            # IFC class, e.g. "IfcBeam"
    cost_code: str              # e.g. "03 30 00"
    description: str
    unit: str                   # the quantity to bill on: length|area|volume|weight|count
    unit_cost: float


def _quantities(el) -> dict[str, float]:
    qtos = ue.get_psets(el, qtos_only=True)
    out: dict[str, float] = {}
    for qset in qtos.values():
        for canonical, keys in _QTY_KEYS.items():
            if canonical in out:
                continue
            for k in keys:
                if k in qset and isinstance(qset[k], (int, float)):
                    out[canonical] = float(qset[k])
                    break
    return out


# How an estimator measures each class. A quantity surveyor prices a roof by the area you could
# walk on and a wall by the face you could paint — never by the total skin of the solid, which is
# what a mesh's surface area is. Getting this wrong does not fail; it just doubles the money.
_PLAN_AREA = ("IfcSlab", "IfcRoof", "IfcPlate", "IfcCovering", "IfcFooting", "IfcPavement")
_FACE_AREA = ("IfcWall", "IfcCurtainWall", "IfcWindow", "IfcDoor", "IfcPanel", "IfcMember")


def _bbox_dims(geo) -> tuple[float, float, float] | None:
    """(dx, dy, dz) of the meshed solid's axis-aligned bounding box, or None if it has no vertices.

    Same lifetime rule as `_bbox_longest`: `geo.verts` is a view into the owning shape."""
    try:
        verts = _np.asarray(geo.verts, dtype=float).reshape(-1, 3)
        if verts.size == 0:
            return None
        e = verts.max(axis=0) - verts.min(axis=0)
        return float(e[0]), float(e[1]), float(e[2])
    except Exception:   # noqa: BLE001 — a mesh we cannot measure is not an error, just unmeasured
        return None


def _measured_area(element, geo) -> float:
    """The area an estimate should price, chosen by what the element IS.

    **This is not the mesh's surface area, and that distinction is the whole point.**
    `ifcopenshell.util.shape.get_area` sums every triangle — for a 12x8 roof slab it returns both
    faces plus the edge band (202 m² for a 96 m² roof), and for four walls around that footprint it
    returns all six faces of each (236 m² where the paintable face is 108). Priced per m², that is
    roughly a doubling of every area line, silently, on models that carry no `Qto_*` base quantities —
    which is precisely the models this application authors itself.

    - **Plan-measured** (slabs, roofs, coverings, footings): the horizontal footprint, dx x dy.
    - **Face-measured** (walls, curtain walls, doors, windows, panels): the elevation face — the
      longer horizontal run x the height. One face, not two, and no edges.
    - Anything else keeps the full surface area, which is the honest answer for a duct or a pipe
      fitting where "the area" genuinely is its skin.

    Falls back to the surface area whenever the bounding box cannot be read, because a slightly
    wrong number beats no number in a takeoff — but the class-aware path is the one that runs.
    """
    surface = float(_shape.get_area(geo))
    dims = _bbox_dims(geo)
    if dims is None:
        return surface
    dx, dy, dz = dims
    if element.is_a() in _PLAN_AREA or any(element.is_a(c) for c in _PLAN_AREA):
        return dx * dy
    if element.is_a() in _FACE_AREA or any(element.is_a(c) for c in _FACE_AREA):
        return max(dx, dy) * dz
    return surface


def _bbox_longest(geo) -> float | None:
    """Longest bounding-box dimension of a meshed geometry — a robust length proxy for
    linear elements (a swept solid's run is its dominant extent). Works whether the run is
    the extrusion depth (vertical pipe/cable riser) or lies in the profile plane (a railing
    extruded to its rail height). Returns None if the mesh has no vertices.

    NOTE: `geo.verts` is only valid while the owning shape is alive, so callers must keep the
    shape referenced until this returns (see `_geom_quantities`)."""
    try:
        verts = _np.asarray(geo.verts, dtype=float).reshape(-1, 3)
        if verts.size == 0:
            return None
        extents = verts.max(axis=0) - verts.min(axis=0)
        return float(extents.max())
    except Exception:
        return None


def _geom_quantities(element, settings) -> dict[str, float]:
    """Geometry-derived fallback when IfcElementQuantity is missing (guide §8).

    Also derives a `length` from the meshed solid's longest bounding-box dimension. Linear
    elements (IfcPipeSegment / IfcDuctSegment / IfcCableCarrierSegment / IfcRailing) are modelled
    as swept solids with no Qto length, so without this they price at $0 on a per-length rate."""
    if not _GEOM_OK:
        return {}
    try:
        shape = _geom.create_shape(settings, element)
        geo = shape.geometry  # keep `shape` alive: geo.verts is a view into it
        out = {
            "volume": float(_shape.get_volume(geo)),
            "area": _measured_area(element, geo),
        }
        length = _bbox_longest(geo)
        if length is not None:
            out["length"] = length
        return out
    except Exception:
        return {}


_STEEL_DENSITY = 7850.0   # kg/m3 — rebar weight fallback when NetWeight is absent


def discipline_summary(model: ifcopenshell.file, settings=None) -> dict[str, Any]:
    """Discipline quantity roll-up (Koh rebar viz / WithRebar-style MEP takeoff): reinforcement
    tonnage, MEP linear runs (duct / pipe / cable), and structural element volume — from Qto psets
    with a geometry fallback. Honest: weights fall back to volume × steel density when not modelled."""
    if settings is None and _GEOM_OK:
        settings = _geom.settings()

    def _q(el) -> dict[str, float]:
        q = _quantities(el)
        if ("volume" not in q or "length" not in q) and settings:
            q = {**_geom_quantities(el, settings), **q}   # psets win; geometry fills gaps
        return q

    def _len(el) -> float:
        return _q(el).get("length", 0.0) or 0.0

    def _weight(el) -> float:
        q = _q(el)
        return q["weight"] if q.get("weight") else (q.get("volume", 0.0) or 0.0) * _STEEL_DENSITY

    def _count(*classes) -> int:
        return sum(len(model.by_type(c)) for c in classes)

    rebar_els = [e for c in ("IfcReinforcingBar", "IfcReinforcingMesh", "IfcTendon") for e in model.by_type(c)]
    rebar_kg = sum(_weight(e) for e in rebar_els)
    duct_m = sum(_len(e) for e in model.by_type("IfcDuctSegment"))
    pipe_m = sum(_len(e) for e in model.by_type("IfcPipeSegment"))
    cable_m = sum(_len(e) for c in ("IfcCableSegment", "IfcCableCarrierSegment") for e in model.by_type(c))
    struct_vol = 0.0
    for c in ("IfcBeam", "IfcColumn", "IfcSlab", "IfcWall", "IfcWallStandardCase", "IfcFooting", "IfcPile"):
        for e in model.by_type(c):
            struct_vol += _q(e).get("volume", 0.0) or 0.0
    return {
        "rebar": {"count": len(rebar_els), "weight_kg": round(rebar_kg, 1),
                  "tonnes": round(rebar_kg / 1000.0, 3),
                  "estimated": not any(_quantities(e).get("weight") for e in rebar_els) and bool(rebar_els)},
        "mep": {"duct_m": round(duct_m, 1), "pipe_m": round(pipe_m, 1), "cable_m": round(cable_m, 1),
                "counts": {"duct": _count("IfcDuctSegment"), "pipe": _count("IfcPipeSegment"),
                           "cable": _count("IfcCableSegment", "IfcCableCarrierSegment"),
                           "fittings": _count("IfcDuctFitting", "IfcPipeFitting", "IfcCableCarrierFitting")}},
        "structure": {"element_volume_m3": round(struct_vol, 2)},
    }


_DISC_CACHE: dict[tuple, dict[str, Any]] = {}
_DISC_CACHE_MAX = 24


def discipline_summary_file(ifc_path: str) -> dict[str, Any]:
    # PERF-3: cache the discipline roll-up keyed on (path, mtime) — discipline_summary falls back to
    # per-element create_shape for volume/length, which re-runs on every /quantities/disciplines GET
    key = (ifc_path, _mtime(ifc_path))
    cached = _DISC_CACHE.get(key)
    if cached is not None:
        return cached
    out = discipline_summary(open_model(ifc_path))
    if len(_DISC_CACHE) >= _DISC_CACHE_MAX:
        _DISC_CACHE.pop(next(iter(_DISC_CACHE)))
    _DISC_CACHE[key] = out
    return out


def load_cost_map(path: str | None) -> dict[str, CostCodeRow]:
    if not path:
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {r["match_class"]: CostCodeRow(**r) for r in data}


def _class_chain(model: ifcopenshell.file, cls: str) -> list[str]:
    """`cls` then each ancestor, most specific first — e.g. IfcWallStandardCase → IfcWall → IfcElement…

    Read from the schema rather than a hand-written table: IFC's hierarchy is large, differs between
    IFC2X3 and IFC4, and a table would be the kind of hand-maintained list that silently stops covering
    new classes. Returns just `[cls]` if the schema cannot be read, so a lookup degrades to today's
    exact match instead of raising.
    """
    try:
        import ifcopenshell.ifcopenshell_wrapper as _w
        decl = _w.schema_by_name(model.schema).declaration_by_name(cls)
    except Exception:                              # noqa: BLE001 — no schema → exact match only
        return [cls]
    chain = []
    while decl is not None:
        chain.append(decl.name())
        decl = decl.supertype()
    return chain


def cost_code_for(model: ifcopenshell.file, el, cost_map: dict[str, CostCodeRow]) -> tuple[Any, str | None]:
    """The cost row for `el`, matched by IFC class **including inherited classes**, plus the key it hit.

    `cost_map.get(el.is_a())` — the exact-string match this replaced — is wrong in a way that produces
    **zero cost silently**. `el.is_a()` returns the CONCRETE class, so a perfectly ordinary cost map
    keyed `IfcWall` matched none of a model's `IfcWallStandardCase` walls: 13 real walls priced at
    nothing, and the takeoff reported them as *uncoded*, which reads as "no cost data was configured"
    rather than "your map does not match this model's classes". Found on `samples/basichouse.ifc`.

    Most specific wins: an exact key beats an ancestor, and a nearer ancestor beats a farther one, so a
    map carrying both `IfcWallStandardCase` and `IfcWall` still gets the intended one. The matched key
    is returned rather than swallowed, so callers can show *which* rule priced an element — a match by
    inheritance is a fact the estimator is entitled to, not an implementation detail.
    """
    for name in _class_chain(model, el.is_a()):
        row = cost_map.get(name)
        if row is not None:
            return row, name
    return None, None


def takeoff(
    model: ifcopenshell.file,
    cost_map: dict[str, CostCodeRow] | None = None,
    geometry_fallback: bool = True,
    force_geometry: bool = False,
) -> list[dict[str, Any]]:
    """`force_geometry`: compute area+volume from geometry for EVERY element that lacks them
    (independent of a cost map), so a model-based estimate prices real quantities even without
    Qto psets or a cost-code mapping. Slightly slower; meant for on-demand estimating."""
    cost_map = cost_map or {}
    settings = None
    if (geometry_fallback or force_geometry) and _GEOM_OK:
        settings = _geom.settings()  # meters, triangulated

    rows: list[dict[str, Any]] = []
    for el in physical_elements(model):
        if el.is_a("IfcOpeningElement"):
            continue
        q = _quantities(el)
        el_type = ue.get_type(el)
        # Matched by inheritance, not by exact class name — see `cost_code_for`. `matched_class` is the
        # cost-map key that actually priced this element; it differs from `ifc_class` exactly when the
        # match came from an ancestor, which is the case that used to price silently at zero.
        cc, matched_class = cost_code_for(model, el, cost_map)

        if force_geometry and settings is not None and ("area" not in q or "volume" not in q):
            for k, v in _geom_quantities(el, settings).items():
                q.setdefault(k, v)

        amount = None
        if cc and cc.unit == "count":
            amount = cc.unit_cost
        else:
            # only compute geometry for elements we'll actually bill and that lack the quantity
            if cc and settings is not None and cc.unit not in q and cc.unit in ("area", "volume"):
                for k, v in _geom_quantities(el, settings).items():
                    q.setdefault(k, v)
            if cc and cc.unit in q:
                amount = round(q[cc.unit] * cc.unit_cost, 2)
        rows.append({
            "guid": el.GlobalId,
            "ifc_class": el.is_a(),
            # Which cost-map key priced this element. Equal to `ifc_class` on an exact hit; an ANCESTOR
            # class when the map was keyed more generally (a map keyed `IfcWall` pricing an
            # `IfcWallStandardCase`); `None` when nothing matched. Surfaced rather than kept internal
            # because "priced by a rule for a different class" is a fact an estimator should be able to
            # see — and because its absence is what made the old exact-match failure invisible.
            "matched_class": matched_class,
            "name": getattr(el, "Name", None),
            "type": getattr(el_type, "Name", None) if el_type else None,
            "storey": storey_name(el),
            "length": q.get("length"),
            "area": q.get("area"),
            "volume": q.get("volume"),
            "weight": q.get("weight"),
            "cost_code": cc.cost_code if cc else None,
            "cost_description": cc.description if cc else None,
            "unit": cc.unit if cc else None,
            "amount": amount,
        })
    return rows


#: R25-QTO-WIRE — how a quantity was obtained. The distinction is the point of this function.
#:
#: `declared` came from an `IfcElementQuantity` the authoring tool wrote: somebody's software asserted
#: that this wall is 12.4 m². `computed` came from meshing the solid and measuring it here: our
#: approximation of the same thing. They are usually close and they are not the same claim, and an
#: estimate that cannot say which is resting on what has lost the ability to be checked.
#:
#: The API layer adds a third, `override`, for a quantity the caller supplied in place of the model's.
#: `fived.estimate` treats an ABSENT source as `unknown` rather than assuming `declared` — a caller
#: who sends quantities with no provenance has said nothing about where they came from, and answering
#: "the model declared these" on their behalf is the overclaim the field exists to prevent.
QUANTITY_SOURCES = ("declared", "computed")

#: Elements meshed in one `measure` call before the geometry pass stops.
#:
#: Meshing is the expensive part — `create_shape` per element — and `measure` is now reachable from a
#: request-serving estimate route that previously did no geometry work at all. On a large tower an
#: uncapped pass is minutes, which turns one estimate into a stalled worker. The cap is REPORTED
#: (`geometry_capped`), never silent: a quantity nobody measured because we ran out of budget looks
#: exactly like one the model never carried, and only one of those is worth chasing.
MAX_GEOMETRY = 20_000


def measure(model: ifcopenshell.file, force_geometry: bool = True,
            max_geometry: int = MAX_GEOMETRY) -> dict[str, Any]:
    """Every element's measurable quantities, keyed by GlobalId — the input `fived.estimate` needs.

    Returns ``{quantities: {guid: {basis: value}}, sources: {guid: {basis: "declared"|"computed"}},
    measured, unmeasured}``.

    This exists so an estimate prices the **model's own** quantities rather than numbers a caller
    passed in. A rate is only as good as what it multiplies: an estimate whose quantities arrive from
    the request body can be internally consistent and still describe a different building.

    An element with no readable quantity is listed in `unmeasured` rather than given zeros. Zero is a
    measurement; "we could not measure it" is not, and billing the second as the first is how an
    estimate ends up confidently missing a floor.
    """
    settings = _geom.settings() if (force_geometry and _GEOM_OK) else None
    quantities: dict[str, dict[str, float]] = {}
    sources: dict[str, dict[str, str]] = {}
    unmeasured: list[dict[str, str]] = []
    meshed = 0
    capped = 0

    for el in physical_elements(model):
        if el.is_a("IfcOpeningElement"):
            continue
        gid = getattr(el, "GlobalId", None)
        if not gid:
            continue
        declared = _quantities(el)
        q: dict[str, float] = dict(declared)
        src = dict.fromkeys(declared, "declared")
        if settings is not None and meshed >= max_geometry:
            capped += 1                       # counted, not skipped in silence — see MAX_GEOMETRY
        elif settings is not None:
            meshed += 1
            for k, v in _geom_quantities(el, settings).items():
                # `setdefault`: a quantity the model DECLARES always beats one we computed. The
                # authoring tool knows what it drew; we know what its triangles came out to.
                if k not in q:
                    q[k] = v
                    src[k] = "computed"
        # `count` is the one basis that needs no measurement — one of a thing is one of a thing — so
        # it is declared, not computed, and never lands in `unmeasured`.
        q["count"] = 1.0
        src["count"] = "declared"
        if len(q) == 1:                       # count only: nothing about this element was measurable
            unmeasured.append({"guid": gid, "ifc_class": el.is_a()})
        quantities[gid] = q
        sources[gid] = src

    return {"quantities": quantities, "sources": sources,
            "measured": len(quantities), "unmeasured": unmeasured,
            "unmeasured_count": len(unmeasured),
            "meshed": meshed, "geometry_capped": capped,
            "note": ("`declared` quantities come from the model's own IfcElementQuantity; `computed` "
                     "ones were measured off the meshed solid here. A declared value always wins.")}


# Takeoff is expensive (geometry meshing with force_geometry) and the same published model is hit
# repeatedly (estimate + QTO export + closeout package). Cache by (path, mtime, …) — a new published
# version writes a new file path, and any in-place change bumps mtime, so the cache is content-safe.
_TAKEOFF_CACHE: dict[tuple, list[dict[str, Any]]] = {}
_TAKEOFF_CACHE_MAX = 24


def _mtime(path: str | None) -> float:
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


def takeoff_file(ifc_path: str, cost_map_path: str | None = None,
                 force_geometry: bool = False) -> list[dict[str, Any]]:
    key = (ifc_path, _mtime(ifc_path), bool(force_geometry), cost_map_path or "", _mtime(cost_map_path))
    cached = _TAKEOFF_CACHE.get(key)
    if cached is not None:
        return cached
    rows = takeoff(open_model(ifc_path), load_cost_map(cost_map_path), force_geometry=force_geometry)
    if len(_TAKEOFF_CACHE) >= _TAKEOFF_CACHE_MAX:
        _TAKEOFF_CACHE.pop(next(iter(_TAKEOFF_CACHE)))   # evict oldest (dict preserves insert order)
    _TAKEOFF_CACHE[key] = rows
    return rows


def element_centroids(model, guids) -> dict:
    """World-space centre of each element, by GlobalId — `{guid: (x, y, z)}`.

    Exists so an issue tied to an element can be *placed* without anyone storing a coordinate. A
    stored anchor is a copy of where the element was; this is where the element **is**, which is the
    only version that survives the element being moved. IFC is the source of truth, so the pin is
    derived from it rather than kept alongside it.

    The centre of the bounding box, not the centroid of mass: for a wall the box centre is the middle
    of the wall, which is where a reader expects the balloon. Elements that cannot be meshed are
    omitted rather than defaulted to the origin — a pin at (0,0) is a pin pointing at the wrong place,
    and the caller can say "not located" instead.
    """
    if not _GEOM_OK or not guids:
        return {}
    want = {g for g in guids if g}
    # WORLD coordinates, and this is the whole correctness of the function. `settings()` defaults
    # `use-world-coords` to False, so `geometry.verts` come back in the element's LOCAL frame with the
    # placement left in `shape.transformation`. Every centroid then lands near the origin — pins that
    # render confidently in the wrong place, which is worse than pins that do not render. The quantity
    # helpers above never noticed because volume and area are placement-invariant; position is not.
    settings = _geom.settings()
    settings.set("use-world-coords", True)
    out: dict = {}
    for el in model.by_type("IfcProduct"):
        gid = getattr(el, "GlobalId", None)
        if gid not in want:
            continue
        try:
            shape = _geom.create_shape(settings, el)
            verts = _np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
            if verts.size:
                lo, hi = verts.min(axis=0), verts.max(axis=0)
                out[gid] = tuple(float(v) for v in (lo + hi) / 2.0)
        except Exception:   # noqa: BLE001 — an unmeshable element is unlocated, not an error
            continue
        if len(out) == len(want):
            break
    return out
