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

This module only establishes the spine (contexts + LOD tag + summary). Deriving coarse Box/Axis/FootPrint
geometry from Body, and consuming these contexts in the drawing generator, are later Wave 11 tracks.
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
