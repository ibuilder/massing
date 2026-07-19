"""W11 · F0 — the representation/context spine + LOD state.

The single architectural foundation the rest of Wave 11 hangs off. Two capabilities:

1. **View-keyed representation contexts.** Beyond the usual Model/Body (3D) context, drawing generation
   and coarse↔fine display need view-specific subcontexts — a `Plan` root plus `Body`/`Annotation`/
   `FootPrint` (PLAN_VIEW) and `Axis`/`Box` subcontexts, each carrying a `TargetView` (and optionally a
   `TargetScale`). One `IfcProduct` can then hold several `IfcShapeRepresentation`s (a full solid `Body`
   for 3D, a single-line `Axis` for schematic plans, a bounding `Box` for massing), and the drawing
   generator selects per element by `(RepresentationIdentifier, TargetView, TargetScale)`.

2. **An element LOD stage.** LOD (100→500) is an element *maturity* state, not a geometry mode — carried
   as `Pset_MassingLOD.Stage`. Advancing LOD refines the same GUID-stable element (real types, more
   Psets, finer Body), it never re-creates it.

F0b adds the **derivation**: `derive_representations` computes each element's local-space bounds from
its Body geometry and authors the coarse views — a `Box` (IfcBoundingBox), an `Axis` centreline
(2-point polyline along the longest horizontal dimension), and a `FootPrint` outline (the bounds
rectangle) — into the matching subcontexts. Deliberately coarse (bounds-based, not a true silhouette):
the point is a cheap view-keyed fallback for massing display and schematic plans, not fine geometry.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api

# The subcontexts the construction-document pipeline expects. Each: (root context_type,
# ContextIdentifier, TargetView). The Model/Body/MODEL_VIEW one already exists in our models.
_SUBCONTEXTS = [
    ("Model", "Body", "MODEL_VIEW"),        # the real 3D solid (streams to Fragments) — usually present
    ("Model", "Axis", "GRAPH_VIEW"),        # centrelines (wall joins, single-line schematic)
    ("Model", "Box", "MODEL_VIEW"),         # bounding-box massing (coarse LOD display)
    ("Plan", "Body", "PLAN_VIEW"),          # 2D cut profile used when a plan drawing is generated
    ("Plan", "Annotation", "PLAN_VIEW"),    # dimensions / tags / keynotes live here
    ("Plan", "FootPrint", "PLAN_VIEW"),     # 2D footprint silhouette
]

_LOD_STAGES = {"100", "200", "300", "350", "400", "500"}


def _find_root(model: ifcopenshell.file, context_type: str):
    """The top-level IfcGeometricRepresentationContext for 'Model' or 'Plan' (not a subcontext)."""
    for c in model.by_type("IfcGeometricRepresentationContext"):
        if c.is_a("IfcGeometricRepresentationSubContext"):
            continue
        if (c.ContextType or "") == context_type:
            return c
    return None


def _find_sub(model: ifcopenshell.file, identifier: str, target_view: str, root):
    for c in model.by_type("IfcGeometricRepresentationSubContext"):
        if (c.ContextIdentifier or "") == identifier and (c.TargetView or "") == target_view \
                and c.ParentContext == root:
            return c
    return None


def ensure_contexts(model: ifcopenshell.file) -> dict:
    """Find-or-create the full view-keyed context tree (Model + Plan roots and the Body/Axis/Box/
    Annotation/FootPrint subcontexts the drawing pipeline needs). Idempotent — safe to run on any model.
    Returns {roots, subcontexts:[{type,identifier,target_view,created}], created} for inspection."""
    roots: dict[str, object] = {}
    for ctype in ("Model", "Plan"):
        r = _find_root(model, ctype)
        if r is None:
            r = ifcopenshell.api.run("context.add_context", model, context_type=ctype)
        roots[ctype] = r

    inventory: list[dict] = []
    created = 0
    for ctype, ident, tview in _SUBCONTEXTS:
        root = roots[ctype]
        sub = _find_sub(model, ident, tview, root)
        was_created = False
        if sub is None:
            sub = ifcopenshell.api.run("context.add_context", model, context_type=ctype,
                                       context_identifier=ident, target_view=tview, parent=root)
            was_created = True
            created += 1
        inventory.append({"type": ctype, "identifier": ident, "target_view": tview,
                          "created": was_created})
    return {"roots": list(roots), "subcontexts": inventory, "created": created}


def set_lod(model: ifcopenshell.file, guids, stage: str = "300") -> int:
    """Tag elements with a **LOD stage** (100/200/300/350/400/500) via `Pset_MassingLOD.Stage`. LOD is
    an element maturity state — the same GUID-stable element carries it as its geometry/data is refined.
    GUID-stable; a bad GUID never aborts the batch. Returns the count tagged."""
    from .edit import set_element_pset

    s = str(stage).strip()
    if s not in _LOD_STAGES:
        raise ValueError(f"LOD stage must be one of {sorted(_LOD_STAGES)}, got {stage!r}")
    n = 0
    for g in guids or []:
        try:
            set_element_pset(model, g, "Pset_MassingLOD", "Stage", s, "str")
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs
            pass
    return n


def _local_bounds(model: ifcopenshell.file, el):
    """The element's axis-aligned bounds in its OWN placement frame (metres), from tessellated Body
    geometry: world verts → inverse local-placement transform. None when it has no shapeable body."""
    import ifcopenshell.geom as geom
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit
    import numpy as np

    try:
        shape = geom.create_shape(geom.settings(), el)
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)   # world, metres
    except Exception:  # noqa: BLE001 — no body geometry → nothing to derive
        return None
    if not verts.size:
        return None
    scale = uunit.calculate_unit_scale(model)
    m4 = np.asarray(uplace.get_local_placement(el.ObjectPlacement), dtype=float)
    m4[:3, 3] *= scale                                     # translation file units → metres
    local = (np.linalg.inv(m4) @ np.hstack([verts, np.ones((len(verts), 1))]).T).T[:, :3]
    return local.min(axis=0), local.max(axis=0)


def derive_representations(model: ifcopenshell.file, guids=None,
                           kinds=("Box", "Axis", "FootPrint")) -> dict:
    """F0b: derive the coarse view-keyed representations from Body geometry — `Box` (IfcBoundingBox in
    Model/Box), `Axis` (a 2-point centreline along the longest horizontal dimension, Model/Axis), and
    `FootPrint` (the bounds rectangle at the element base, Plan/FootPrint). Bounds-based by design (a
    cheap massing/schematic fallback, not a silhouette). Idempotent per element+kind; `guids=None`
    sweeps every physical element; Axis only lands on elements meaningfully linear in plan (the long
    side ≥ 2× the short). Returns per-kind counts."""
    import ifcopenshell.util.unit as uunit

    ctx = ensure_contexts(model)                           # noqa: F841 — guarantees the subcontexts
    scale = uunit.calculate_unit_scale(model)              # metres → file units on the way back in
    box_ctx = _find_sub(model, "Box", "MODEL_VIEW", _find_root(model, "Model"))
    axis_ctx = _find_sub(model, "Axis", "GRAPH_VIEW", _find_root(model, "Model"))
    foot_ctx = _find_sub(model, "FootPrint", "PLAN_VIEW", _find_root(model, "Plan"))

    if guids:
        elements = [e for g in guids if (e := _safe_by_guid(model, g)) is not None]
    else:
        elements = list(model.by_type("IfcElement"))

    counts = {"Box": 0, "Axis": 0, "FootPrint": 0, "skipped_no_body": 0}
    for el in elements:
        if el.is_a("IfcElementType") or el.is_a("IfcFeatureElement"):
            continue
        rep = getattr(el, "Representation", None)
        have = {(r.RepresentationIdentifier or "") for r in (rep.Representations if rep else [])}
        want = [k for k in kinds if k not in have]
        if not want:
            continue
        b = _local_bounds(model, el)
        if b is None:
            counts["skipped_no_body"] += 1
            continue
        mn, mx = b
        dims = (mx - mn)
        f = 1.0 / scale                                    # metres → file units
        new_reps = []
        if "Box" in want and box_ctx is not None and all(d > 1e-9 for d in dims):
            corner = model.create_entity("IfcCartesianPoint",
                                         tuple(float(v) * f for v in mn))
            bb = model.create_entity("IfcBoundingBox", Corner=corner,
                                     XDim=float(dims[0]) * f, YDim=float(dims[1]) * f,
                                     ZDim=float(dims[2]) * f)
            new_reps.append(model.create_entity(
                "IfcShapeRepresentation", ContextOfItems=box_ctx, RepresentationIdentifier="Box",
                RepresentationType="BoundingBox", Items=[bb]))
            counts["Box"] += 1
        long_i = 0 if dims[0] >= dims[1] else 1
        short_i = 1 - long_i
        if ("Axis" in want and axis_ctx is not None
                and dims[long_i] >= 2.0 * max(dims[short_i], 1e-9)):
            mid_s = (mn[short_i] + mx[short_i]) / 2.0
            p0 = [0.0, 0.0]
            p1 = [0.0, 0.0]
            p0[long_i], p0[short_i] = float(mn[long_i]) * f, float(mid_s) * f
            p1[long_i], p1[short_i] = float(mx[long_i]) * f, float(mid_s) * f
            line = model.create_entity("IfcPolyline", Points=[
                model.create_entity("IfcCartesianPoint", tuple(p0)),
                model.create_entity("IfcCartesianPoint", tuple(p1))])
            new_reps.append(model.create_entity(
                "IfcShapeRepresentation", ContextOfItems=axis_ctx, RepresentationIdentifier="Axis",
                RepresentationType="Curve2D", Items=[line]))
            counts["Axis"] += 1
        if "FootPrint" in want and foot_ctx is not None and dims[0] > 1e-9 and dims[1] > 1e-9:
            pts = [(mn[0], mn[1]), (mx[0], mn[1]), (mx[0], mx[1]), (mn[0], mx[1]), (mn[0], mn[1])]
            poly = model.create_entity("IfcPolyline", Points=[
                model.create_entity("IfcCartesianPoint", (float(x) * f, float(y) * f))
                for x, y in pts])
            new_reps.append(model.create_entity(
                "IfcShapeRepresentation", ContextOfItems=foot_ctx,
                RepresentationIdentifier="FootPrint", RepresentationType="Curve2D", Items=[poly]))
            counts["FootPrint"] += 1
        if new_reps:
            if rep is None:
                el.Representation = model.create_entity(
                    "IfcProductDefinitionShape", Representations=new_reps)
            else:
                rep.Representations = list(rep.Representations) + new_reps
    return {"derived": counts, "elements": len(elements)}


def _safe_by_guid(model: ifcopenshell.file, guid: str):
    try:
        return model.by_guid(guid)
    except Exception:  # noqa: BLE001 — a stale GUID never aborts the sweep
        return None


def lod_summary(model: ifcopenshell.file) -> dict:
    """Count physical elements per LOD stage (unset = not yet staged). Feeds an LOD overview and the
    'advance the model' workflow."""
    import ifcopenshell.util.element as ue

    counts = dict.fromkeys(("100", "200", "300", "350", "400", "500"), 0)
    counts["UNSET"] = 0
    total = 0
    for el in model.by_type("IfcElement"):
        total += 1
        ps = ue.get_pset(el, "Pset_MassingLOD") or {}
        stage = str(ps.get("Stage") or "").strip()
        counts[stage if stage in counts else "UNSET"] += 1
    return {"total": total, "counts": counts, "staged": total - counts["UNSET"],
            "prop": "Pset_MassingLOD.Stage"}
