"""REL-3 leaf: low-level IFC authoring primitives shared by every edit recipe.

The context/profile/mesh/lookup helpers that `edit.py`'s recipes (and a few sibling authoring modules —
connections, curtainwall, families) all build on. Pulled out as a pure foundation so recipe groups can be
split off later without importing the whole 2 000-line `edit.py` (they import these primitives here
instead). `edit.py` re-exports every name, so existing `from .edit import _body_context …` importers are
unaffected. Depends only on ifcopenshell — never on a recipe.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api


def _body_context(model):
    return next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                 if c.ContextIdentifier == "Body"), None) or \
        (model.by_type("IfcGeometricRepresentationContext") or [None])[0]


def _rect_profile(model, xdim: float, ydim: float):
    """An IfcRectangleProfileDef (dims given in METRES) WITH a Position. web-ifc requires the profile
    placement to be set (ifcopenshell tolerates a null Position, but web-ifc silently skips the element
    → it renders invisible). NB: geometry.add_profile_representation SI-converts only the extrusion
    *depth*, not the profile — so profile dims must be authored in **file units** (metres ÷ unit_scale),
    else a wall/column is 1000× too thin on a millimetre model."""
    import ifcopenshell.util.unit as uunit
    scale = uunit.calculate_unit_scale(model)          # metres per file unit (1 for m, 0.001 for mm)
    pos = model.create_entity("IfcAxis2Placement2D",
                              Location=model.create_entity("IfcCartesianPoint", (0.0, 0.0)),
                              RefDirection=model.create_entity("IfcDirection", (1.0, 0.0)))
    return model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos,
                               XDim=float(xdim) / scale, YDim=float(ydim) / scale)


def _first_storey(model, name=None):
    sts = sorted(model.by_type("IfcBuildingStorey"),
                 key=lambda s: float(getattr(s, "Elevation", 0) or 0))
    if name:
        return next((s for s in sts if s.Name == name), sts[0] if sts else None)
    return sts[0] if sts else None


def _box_mesh(cx: float, cy: float, w: float, d: float, h: float):
    """verts/faces (0-based) for an axis-aligned box centred at (cx,cy) in plan, base at z=0, size w×d×h."""
    hw, hd = w / 2.0, d / 2.0
    v = [[cx - hw, cy - hd, 0], [cx + hw, cy - hd, 0], [cx + hw, cy + hd, 0], [cx - hw, cy + hd, 0],
         [cx - hw, cy - hd, h], [cx + hw, cy - hd, h], [cx + hw, cy + hd, h], [cx - hw, cy + hd, h]]
    f = [[0, 2, 1], [0, 3, 2],            # base
         [4, 5, 6], [4, 6, 7],            # top
         [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],   # sides
         [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
    return v, f


def _annotation_context(model):
    """The 2D Annotation representation subcontext (from representations.ensure_contexts), root as fallback."""
    ctx = next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                if c.ContextIdentifier == "Annotation"), None)
    if ctx is None:
        try:
            from . import representations as reps
            reps.ensure_contexts(model)
            ctx = next((c for c in model.by_type("IfcGeometricRepresentationSubContext")
                        if c.ContextIdentifier == "Annotation"), None)
        except Exception:                              # noqa: BLE001
            pass
    return ctx or (model.by_type("IfcGeometricRepresentationContext") or [None])[0]


def _element_mark(el) -> str:
    """A short tag label for an element: its Name, else a Pset 'Reference'/'Tag' mark, else its type name,
    else the IFC class short-name (IfcWall → Wall). Element-aware — the tag reflects the element."""
    import ifcopenshell.util.element as ue

    name = (getattr(el, "Name", None) or "").strip()
    if name:
        return name
    try:
        psets = ue.get_psets(el) or {}
        for props in psets.values():
            for key in ("Reference", "Tag", "Mark"):
                v = props.get(key)
                if v:
                    return str(v)
    except Exception:                                  # noqa: BLE001 — psets best-effort
        pass
    tag = (getattr(el, "Tag", None) or "").strip() if hasattr(el, "Tag") else ""
    if tag:
        return tag
    try:
        t = ue.get_type(el)
        if t is not None and getattr(t, "Name", None):
            return str(t.Name)
    except Exception:                                  # noqa: BLE001
        pass
    return el.is_a()[3:] if el.is_a().startswith("Ifc") else el.is_a()


def _wall_thickness(host, default: float = 0.2) -> float:
    """The host wall's thickness (m) for sizing a door/window lining — from Qto_WallBaseQuantities if
    present, else a sensible default."""
    import ifcopenshell.util.element as ue

    q = ue.get_pset(host, "Qto_WallBaseQuantities") or {}
    w = q.get("Width")
    try:
        return float(w) if w else default
    except (TypeError, ValueError):
        return default


def _fill_representation(model, body, kind: str, width: float, height: float,
                        operation: str | None, scale: float, lining_depth: float):
    """B2 — parametric door/window geometry via IfcOpenShell's built-in generators (real lining, frame
    and panels — a LOD 300→350 jump over the old single box proxy). Returns a shape representation, or
    None so the caller falls back to the box proxy if the generator rejects the parameters."""
    try:
        if kind == "window":
            return ifcopenshell.api.run(
                "geometry.add_window_representation", model, context=body,
                overall_height=float(height), overall_width=float(width),
                partition_type=(operation or "SINGLE_PANEL"),
                lining_properties={"LiningDepth": lining_depth, "LiningThickness": 0.05,
                                   "MullionThickness": 0.0, "TransomThickness": 0.0},
                panel_properties=[{"FrameDepth": 0.04, "FrameThickness": 0.05}],
                unit_scale=scale)
        return ifcopenshell.api.run(
            "geometry.add_door_representation", model, context=body,
            overall_height=float(height), overall_width=float(width),
            operation_type=(operation or "SINGLE_SWING_LEFT"),
            lining_properties={"LiningDepth": lining_depth, "LiningThickness": 0.05,
                               "TransomThickness": 0.0},
            panel_properties={"PanelDepth": 0.04, "PanelWidth": 1.0,
                              "FrameDepth": 0.0, "FrameThickness": 0.0},
            unit_scale=scale)
    except Exception:  # noqa: BLE001 — bad enum / generator failure → caller uses the box proxy
        return None


def _element(model: ifcopenshell.file, guid: str):
    el = next((e for e in model.by_type("IfcElement") if e.GlobalId == guid), None)
    if el is None:
        raise ValueError(f"element {guid} not found")
    return el
