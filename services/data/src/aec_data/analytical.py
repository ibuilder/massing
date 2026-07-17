"""W10-7 · structural analytical model — the analytical layer alongside the physical (LOD 300) model.

A physical `IfcColumn`/`IfcBeam` is a solid; its *analytical* idealisation is a 1-D line member between
two nodes, the thing a structural solver actually consumes. This module derives an
`IfcStructuralAnalysisModel` from the physical frame:

- each column / beam  → an `IfcStructuralCurveMember` (an `IfcEdge` topology between two shared nodes),
- each distinct member end → a shared `IfcStructuralPointConnection` (an `IfcVertexPoint` node),
- a default gravity `IfcStructuralLoadCase` + `IfcStructuralLoadGroup` (self-weight, permanent G),
- the analytical member is linked back to its physical element (`IfcRelAssignsToProduct`), GUID-stable.

Slice 1 covers the frame (curve members + nodes + load case). Surface members (slabs/walls →
`IfcStructuralSurfaceMember`) and per-member load activities are later slices. Pure ifcopenshell — the
analytical model is topology (vertices/edges), so no geometry kernel is needed.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as _ue
import ifcopenshell.util.placement as _pl
import ifcopenshell.util.unit as _uu

# physical classes that idealise to a 1-D analytical curve member (the frame)
_CURVE_CLASSES = ("IfcColumn", "IfcBeam", "IfcMember")

# top-level analytical entities purged (deep) once every referencing rel is gone, so derive is idempotent
_ANALYTICAL_ITEMS = ("IfcStructuralCurveMember", "IfcStructuralSurfaceMember",
                     "IfcStructuralPointConnection", "IfcStructuralCurveConnection",
                     "IfcStructuralAnalysisModel", "IfcStructuralLoadGroup", "IfcStructuralLoadCase")


def _purge_analytical(model: ifcopenshell.file) -> None:
    """Remove every analytical entity so a re-derive rebuilds cleanly instead of accumulating. First drop
    all rels that reference analytical items (member connections, group + product assignments) — while
    those inverses remain, `remove_deep2` won't remove the item — then deep-remove the items (which frees
    their owned topology reps; `remove_deep2` keeps a node still shared by another element)."""
    def _is_struct(o):
        return bool(getattr(o, "is_a", None)) and (o.is_a("IfcStructuralItem") or o.is_a("IfcStructuralAnalysisModel"))

    for rel in list(model.by_type("IfcRelConnectsStructuralMember")):
        model.remove(rel)
    for rel in list(model.by_type("IfcRelConnectsStructuralActivity")):
        model.remove(rel)
    for rel in list(model.by_type("IfcRelAssignsToGroup")):
        if getattr(rel, "RelatingGroup", None) and rel.RelatingGroup.is_a("IfcStructuralAnalysisModel"):
            model.remove(rel)
    for rel in list(model.by_type("IfcRelAssignsToProduct")):
        if any(_is_struct(o) for o in (rel.RelatedObjects or [])):
            model.remove(rel)
    for tname in _ANALYTICAL_ITEMS:
        for ent in list(model.by_type(tname)):
            try:
                _ue.remove_deep2(model, ent)
            except Exception:  # noqa: BLE001 — already freed as a shared child of a prior deep-remove
                pass


def _model_context(model: ifcopenshell.file):
    """A geometric representation context for the analytical topology reps — the Model root context
    (topology items reference a context but carry their own coordinates)."""
    for c in model.by_type("IfcGeometricRepresentationContext"):
        if c.is_a("IfcGeometricRepresentationSubContext"):
            continue
        if (c.ContextType or "") == "Model":
            return c
    ctxs = [c for c in model.by_type("IfcGeometricRepresentationContext")
            if not c.is_a("IfcGeometricRepresentationSubContext")]
    return ctxs[0] if ctxs else None


def _axis_endpoints(el, scale: float):
    """The (start, end) of a swept member's centreline in FILE units, from its extruded Body: the object
    placement origin, and origin + (rotation · ExtrudedDirection·Depth). Returns None if not a simple
    extrusion. `scale` (m/file-unit) is unused here (we stay in file units) but kept for call symmetry."""
    import numpy as np

    rep = getattr(el, "Representation", None)
    if rep is None:
        return None
    body = next((r for r in rep.Representations if r.RepresentationIdentifier == "Body"), None)
    if body is None or not body.Items:
        return None
    solid = body.Items[0]
    if not solid.is_a("IfcExtrudedAreaSolid"):
        return None
    M = np.array(_pl.get_local_placement(el.ObjectPlacement), dtype=float)   # file units
    origin = M[:3, 3]
    axis_local = np.array(solid.ExtrudedDirection.DirectionRatios, dtype=float) * float(solid.Depth)
    end = origin + M[:3, :3] @ axis_local
    return tuple(round(float(v), 4) for v in origin), tuple(round(float(v), 4) for v in end)


def _perp_axis(a, b):
    """A reference axis (local z, IfcDirection ratios) perpendicular-ish to the member a→b: for a mostly
    vertical member use global X, otherwise global Z. Enough to orient the section for a v1 model."""
    dz = abs(b[2] - a[2])
    horiz = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
    return (1.0, 0.0, 0.0) if dz > horiz else (0.0, 0.0, 1.0)


def derive_analytical(model: ifcopenshell.file, name: str = "Analytical model") -> dict:
    """Build an `IfcStructuralAnalysisModel` from the physical frame (columns + beams). Idempotent-ish:
    a prior analysis model of the same name is removed first so re-running refreshes it. Returns
    {analysis_model (guid), curve_members, nodes, load_case, load_group}."""
    api = ifcopenshell.api.run
    scale = _uu.calculate_unit_scale(model)
    ctx = _model_context(model)

    _purge_analytical(model)     # refresh: wipe any prior analytical entities so the derive is repeatable
    amodel = api("structural.add_structural_analysis_model", model)
    api("structural.edit_structural_analysis_model", model, structural_analysis_model=amodel,
        attributes={"Name": name, "PredefinedType": "LOADING_3D"})

    nodes: dict[tuple, object] = {}      # rounded file-unit coord -> IfcStructuralPointConnection
    members: list[object] = []
    assigned: list[object] = []

    def _node(coord):
        key = tuple(round(c, 3) for c in coord)
        pc = nodes.get(key)
        if pc is None:
            cp = model.create_entity("IfcCartesianPoint", Coordinates=tuple(float(c) for c in coord))
            vp = model.create_entity("IfcVertexPoint", VertexGeometry=cp)
            topo = model.create_entity("IfcTopologyRepresentation", ContextOfItems=ctx,
                                       RepresentationIdentifier="Reference", RepresentationType="Vertex",
                                       Items=[vp])
            pc = api("root.create_entity", model, ifc_class="IfcStructuralPointConnection",
                     name=f"N{len(nodes) + 1}")
            pc.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[topo])
            nodes[key] = pc
            assigned.append(pc)
            _node.vertex[key] = vp
        return nodes[key], _node.vertex[key]
    _node.vertex = {}

    for cls in _CURVE_CLASSES:
        for el in model.by_type(cls):
            if el.is_a("IfcElementType"):
                continue
            ends = _axis_endpoints(el, scale)
            if ends is None:
                continue
            a, b = ends
            if a == b:
                continue
            pc_a, vp_a = _node(a)
            pc_b, vp_b = _node(b)
            edge = model.create_entity("IfcEdge", EdgeStart=vp_a, EdgeEnd=vp_b)
            topo = model.create_entity("IfcTopologyRepresentation", ContextOfItems=ctx,
                                       RepresentationIdentifier="Reference", RepresentationType="Edge",
                                       Items=[edge])
            cm = api("root.create_entity", model, ifc_class="IfcStructuralCurveMember",
                     name=(getattr(el, "Name", None) or el.is_a()))
            cm.PredefinedType = "RIGID_JOINED_MEMBER"
            cm.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[topo])
            cm.Axis = model.create_entity("IfcDirection", DirectionRatios=_perp_axis(a, b))   # section ref axis
            api("structural.add_structural_member_connection", model, relating_structural_member=cm,
                related_structural_connection=pc_a)
            api("structural.add_structural_member_connection", model, relating_structural_member=cm,
                related_structural_connection=pc_b)
            api("structural.assign_product", model, relating_product=el, related_object=cm)  # analytical↔physical
            members.append(cm)
            assigned.append(cm)

    if assigned:
        api("structural.assign_structural_analysis_model", model, products=assigned,
            structural_analysis_model=amodel)

    # a default gravity load case (permanent self-weight) + its load group — the "load cases" of W10-7
    lgroup = api("structural.add_structural_load_group", model, name="Self weight",
                 action_type="PERMANENT_G", action_source="DEAD_LOAD_G")
    lcase = api("structural.add_structural_load_case", model, name="Dead load (self weight)",
                action_type="PERMANENT_G", action_source="DEAD_LOAD_G")
    try:
        api("structural.edit_structural_analysis_model", model, structural_analysis_model=amodel,
            attributes={"LoadedBy": [lgroup]})
    except Exception:  # noqa: BLE001 — LoadedBy wiring is best-effort
        pass

    return {"analysis_model": amodel.GlobalId, "curve_members": len(members), "nodes": len(nodes),
            "load_case": getattr(lcase, "Name", None), "load_group": getattr(lgroup, "Name", None)}


def summary(model: ifcopenshell.file) -> dict:
    """Read back the analytical model(s): counts of analysis models, curve/surface members, point
    connections, and load cases/groups — feeds an analytical-model overview + the 'derive' workflow."""
    amodels = model.by_type("IfcStructuralAnalysisModel")
    curve = model.by_type("IfcStructuralCurveMember")
    surface = model.by_type("IfcStructuralSurfaceMember")
    nodes = model.by_type("IfcStructuralPointConnection")
    cases = model.by_type("IfcStructuralLoadCase")
    groups = model.by_type("IfcStructuralLoadGroup")
    return {
        "analysis_models": [{"guid": a.GlobalId, "name": getattr(a, "Name", None),
                             "predefined_type": getattr(a, "PredefinedType", None)} for a in amodels],
        "curve_members": len(curve),
        "surface_members": len(surface),
        "point_connections": len(nodes),
        "load_cases": [getattr(c, "Name", None) for c in cases],
        "load_groups": [getattr(g, "Name", None) for g in groups],
        "has_model": len(amodels) > 0,
    }
