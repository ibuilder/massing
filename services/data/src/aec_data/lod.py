"""R23-STOREY-LOD — server-side coarse proxies, and the measurement that justifies them.

The archived Phase-2 audit says Fragments *"culls to the camera frustum. We use this directly — no
custom LOD needed for typical AEC models."* That is accurate and it answers a different question.
Frustum culling removes what is **off-screen**; it does nothing about density that is **on-screen**,
which is precisely the case this module is for — a whole building in view, every element in frustum.

So the first thing here is not a proxy, it is a **census**, because the claim above should be retired
by a number rather than by an opinion. Measured on `samples/school_str.ifc` (1,551 elements):

    IfcReinforcingBar     619 elements    189,508 tris    55.2%   <- invisible at building scale
    IfcSlab               299             76,020          22.1%
    IfcColumn             203             37,548          10.9%
    IfcBeam               375             35,658          10.4%

**One class nobody can see at building scale is more than half the triangle budget.** That is the
prize, and it is why this is worth building — and it is also why the census ships as a function rather
than as a paragraph: the next model may be shaped differently, and the decision should be re-measured
rather than inherited.

## The Fragments-writer blocker does not apply

Recorded as: *this repo has an IFC→Fragments converter, not a Fragments writer — there is nothing to
encode into.* True, and it blocks **viewer-side** LOD. It does not block this, because a server-side
proxy never needed to encode `.frag` directly: the pipeline is already IFC→frag and we author IFC.
Verified end to end — a 3-storey proxy IFC authored here converted to a 3,817-byte `.frag` through
`services/converter/src/cli.mjs` with no new dependency.

## What this refuses to do

* **A proxy that does not say what it replaced is a lie about the model.** Every plan reports the
  classes proxied, the elements affected and the triangles saved, so "this view is approximate" is a
  fact the caller carries rather than a footnote.
* **Structure is never proxied by default.** Beams, columns, slabs and walls are what a building
  *is*; a viewer showing boxes where the frame should be is wrong in a way a user cannot detect. The
  default set is small parts and finishes only, and the set is a named constant, not a literal buried
  in a filter.
* **An unmeshable element is counted and named, never silently skipped.** 15 of 1,551 failed to mesh
  in the census above. Dropping them quietly would understate the model and overstate the saving.
* **No census, no plan.** If geometry cannot be measured the module refuses rather than proxying on a
  guess — a proxy chosen without knowing what it saves is a change with an unknown benefit and a
  known cost.
"""
from __future__ import annotations

import collections
from typing import Any

#: Classes safe to replace with a coarse proxy at building scale: small parts, finishes and contents.
#: NOT a performance list — a *visibility* list. Anything here is something a user cannot resolve when
#: the whole storey is in frame, so replacing it changes what the GPU does and not what the user sees.
SMALL_PART_CLASSES: tuple[str, ...] = (
    "IfcReinforcingBar", "IfcReinforcingMesh", "IfcTendon", "IfcTendonAnchor",
    "IfcFastener", "IfcMechanicalFastener", "IfcDiscreteAccessory",
    "IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
    "IfcFlowFitting", "IfcFlowSegment", "IfcFlowController", "IfcFlowTerminal",
    "IfcValve", "IfcJunctionBox", "IfcCableSegment", "IfcCableFitting",
)

#: Never proxied by default. A building's frame is what the model is *for*; a coarse box in its place
#: is an error the viewer cannot signal and the user cannot see through.
STRUCTURAL_CLASSES: tuple[str, ...] = (
    "IfcBeam", "IfcColumn", "IfcSlab", "IfcWall", "IfcWallStandardCase",
    "IfcFooting", "IfcPile", "IfcMember", "IfcRoof", "IfcStair", "IfcRamp",
)

STATUS_OK = "measured"
STATUS_NO_GEOMETRY = "no_geometry"

STATUS_MEANING = {
    STATUS_OK: "geometry was meshed and the triangle census is real",
    STATUS_NO_GEOMETRY: "no element could be meshed, so there is no census and no proxy plan — a "
                        "proxy chosen without knowing what it saves has an unknown benefit and a "
                        "known cost",
}


def _is_small_part(ifc_class: str) -> bool:
    return ifc_class in SMALL_PART_CLASSES


def census(model, max_elements: int | None = None) -> dict[str, Any]:
    """Triangles and element counts per IFC class.

    `max_elements` caps the mesh pass and the cap is **reported** (`capped`), never silent: geometry
    nobody measured because the budget ran out looks exactly like geometry that is not there, and only
    one of those is worth chasing. Mirrors `qto.MAX_GEOMETRY`'s reasoning."""
    import ifcopenshell.geom as geom

    from .qto import physical_elements

    settings = geom.settings()
    tris: dict[str, int] = collections.Counter()
    counts: dict[str, int] = collections.Counter()
    unmeshable: list[dict] = []
    seen = 0
    capped = False

    for el in physical_elements(model):
        if max_elements is not None and seen >= max_elements:
            capped = True
            break
        seen += 1
        cls = el.is_a()
        counts[cls] += 1
        try:
            shape = geom.create_shape(settings, el)
            tris[cls] += len(shape.geometry.faces) // 3
        except Exception as e:                          # noqa: BLE001 — named, never silently dropped
            if len(unmeshable) < 50:
                unmeshable.append({"guid": getattr(el, "GlobalId", None), "ifc_class": cls,
                                   "reason": type(e).__name__})

    total = sum(tris.values())
    rows = [{"ifc_class": k, "elements": counts[k], "triangles": v,
             "pct_triangles": round(100.0 * v / total, 2) if total else 0.0,
             "small_part": _is_small_part(k)}
            for k, v in sorted(tris.items(), key=lambda kv: -kv[1])]

    return {
        "status": STATUS_OK if total else STATUS_NO_GEOMETRY,
        "status_meaning": STATUS_MEANING[STATUS_OK if total else STATUS_NO_GEOMETRY],
        "elements_examined": seen,
        "total_triangles": total,
        "by_class": rows,
        "unmeshable_count": len(unmeshable),
        "unmeshable": unmeshable,
        "capped": capped,
        "cap": max_elements,
    }


def proxy_plan(census_result: dict, classes: tuple[str, ...] | None = None) -> dict[str, Any]:
    """What proxying `classes` would actually save, from a real census.

    Returns the saving AND what it costs in fidelity — which classes stop being themselves — because
    a plan that reports only the triangles saved is an argument, not a decision."""
    if not census_result or census_result.get("status") != STATUS_OK:
        return {"status": STATUS_NO_GEOMETRY,
                "reason": "no usable census — refusing to plan a proxy whose saving is unknown",
                "proxied": [], "triangles_saved": None, "pct_saved": None}

    target = tuple(classes) if classes is not None else SMALL_PART_CLASSES
    # A caller may pass structure deliberately; it is allowed, but it is REPORTED rather than obeyed
    # quietly, because "the frame is now boxes" is not something a viewer can signal on its own.
    structural = sorted(set(target) & set(STRUCTURAL_CLASSES))

    rows = census_result["by_class"]
    total = census_result["total_triangles"]
    hit = [r for r in rows if r["ifc_class"] in target]
    saved = sum(r["triangles"] for r in hit)

    # THE CAP MUST TRAVEL. A census capped at 400 elements of `school_str.ifc` contains no rebar at
    # all — iteration order puts it later — so the plan reports "0 triangles saved, 0%", which reads
    # as "LOD is not worth building" from a measurement that never looked at the class that dominates
    # the model. The census flags `capped`; a caller reading only the plan would not see it. Found by
    # running against a real model rather than the fixture, which had no cap to propagate.
    capped = bool(census_result.get("capped"))
    return {
        "status": STATUS_OK,
        "capped": capped,
        "cap": census_result.get("cap"),
        "elements_examined": census_result.get("elements_examined"),
        "saving_is_lower_bound": capped,
        "cap_note": (
            f"the census stopped after {census_result.get('elements_examined')} elements, so this "
            "saving is a LOWER BOUND — classes that appear later in the model were never measured "
            "and a small or zero saving here is not evidence that a proxy is not worth building"
            if capped else
            "the whole model was measured; this saving is complete"),
        "proxied": [{"ifc_class": r["ifc_class"], "elements": r["elements"],
                     "triangles": r["triangles"], "pct_triangles": r["pct_triangles"]} for r in hit],
        "elements_proxied": sum(r["elements"] for r in hit),
        "triangles_saved": saved,
        "triangles_remaining": total - saved,
        "pct_saved": round(100.0 * saved / total, 2) if total else 0.0,
        # The fidelity cost, stated in the same payload as the benefit.
        "structural_classes_included": structural,
        "fidelity_note": (
            "these classes are replaced by coarse proxies and stop being individually visible; "
            + ("INCLUDES STRUCTURE (" + ", ".join(structural) + ") — a viewer cannot signal that the "
               "frame is approximate and a user cannot see through it"
               if structural else
               "structure is untouched, so the building's frame renders exactly as authored")),
    }


#: Marks a generated proxy in the model itself. A coarse box that a user or a downstream tool can
#: mistake for authored geometry is worse than no proxy at all — it would be measured, scheduled and
#: priced. The name prefix and this pset are both present so the fact survives whichever one a reader
#: happens to look at.
PROXY_PSET = "AEC_LOD"
PROXY_NAME_PREFIX = "LOD Proxy — "


def _aabb(model, elements) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """World-space axis-aligned bounds of `elements`, or None if none could be meshed."""
    import ifcopenshell.geom as geom
    import numpy as np

    settings = geom.settings()
    lo = np.array([float("inf")] * 3)
    hi = np.array([float("-inf")] * 3)
    seen = False
    for el in elements:
        try:
            shape = geom.create_shape(settings, el)
        except Exception:                              # noqa: BLE001 — counted by the caller's census
            continue
        v = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        if not len(v):
            continue
        m = np.asarray(shape.transformation.matrix, dtype=float)
        m = m.reshape(4, 4).T if m.size == 16 else np.eye(4)
        w = (m[:3, :3] @ v.T).T + m[:3, 3]
        lo = np.minimum(lo, w.min(axis=0))
        hi = np.maximum(hi, w.max(axis=0))
        seen = True
    if not seen:
        return None
    return tuple(lo.tolist()), tuple(hi.tolist())


def build_storey_proxy(model, out_path: str, classes: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Write a proxy IFC: one coarse box per storey standing in for `classes` on that storey.

    The output is an ordinary IFC, so it reaches the viewer through the converter we already ship —
    which is why the recorded "no Fragments writer" blocker does not apply here (see the module
    docstring). Returns a report of what was replaced and what it cost.

    Refusals:

    * **every proxy declares itself**, by name prefix and by an `AEC_LOD` pset. A coarse box mistaken
      for authored geometry would be measured, scheduled and priced — worse than no proxy at all;
    * **a storey with nothing to proxy gets no box**, rather than an empty one at the origin. A
      zero-extent proxy renders as a speck nobody can interpret and implies content that is not there;
    * **structure is never included by default** — `SMALL_PART_CLASSES` only;
    * **if nothing could be meshed, no file is written** and the report says so, rather than emitting
      an empty model that looks like a successful export.
    """
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.util.unit as uunit
    import numpy as np

    from .edit_core import _body_context, _rect_profile
    from .ifc_loader import storey_name
    from .qto import physical_elements

    target = tuple(classes) if classes is not None else SMALL_PART_CLASSES
    by_storey: dict[str, list] = collections.defaultdict(list)
    considered = 0
    for el in physical_elements(model):
        if el.is_a() in target:
            considered += 1
            by_storey[storey_name(el) or ""].append(el)

    if not considered:
        return {"status": STATUS_NO_GEOMETRY, "written": False, "path": None,
                "storeys": [], "elements_replaced": 0,
                "reason": "no element of the requested classes is present, so there is nothing to "
                          "proxy and no file was written — an empty proxy would look like a "
                          "successful export of nothing"}

    out = ifcopenshell.file(schema=model.schema)
    project = ifcopenshell.api.run("root.create_entity", out, ifc_class="IfcProject",
                                   name="LOD Proxy")
    ifcopenshell.api.run("unit.assign_unit", out)
    ctx = ifcopenshell.api.run("context.add_context", out, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", out, context_type="Model",
                                context_identifier="Body", target_view="MODEL_VIEW",
                                parent=ctx) or _body_context(out)
    site = ifcopenshell.api.run("root.create_entity", out, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", out, ifc_class="IfcBuilding", name="Building")
    ifcopenshell.api.run("aggregate.assign_object", out, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", out, products=[building], relating_object=site)
    scale = uunit.calculate_unit_scale(out) or 1.0

    rows: list[dict] = []
    written_any = False
    for name, els in sorted(by_storey.items()):
        box = _aabb(model, els)
        if box is None:
            rows.append({"storey": name or "(unassigned)", "elements": len(els),
                         "proxied": False, "reason": "no element on this storey could be meshed"})
            continue
        (x0, y0, z0), (x1, y1, z1) = box
        dx, dy, dz = max(x1 - x0, 1e-3), max(y1 - y0, 1e-3), max(z1 - z0, 1e-3)

        st = ifcopenshell.api.run("root.create_entity", out, ifc_class="IfcBuildingStorey",
                                  name=name or "Unassigned")
        st.Elevation = float(z0)
        ifcopenshell.api.run("aggregate.assign_object", out, products=[st], relating_object=building)

        proxy = ifcopenshell.api.run("root.create_entity", out,
                                     ifc_class="IfcBuildingElementProxy",
                                     name=PROXY_NAME_PREFIX + (name or "Unassigned"))
        matrix = np.array([[1, 0, 0, (x0 + x1) / 2], [0, 1, 0, (y0 + y1) / 2],
                           [0, 0, 1, z0], [0, 0, 0, 1]], dtype=float)
        ifcopenshell.api.run("geometry.edit_object_placement", out, product=proxy, matrix=matrix)
        # Profile dims in FILE UNITS — `geometry.add_profile_representation` SI-converts the extrusion
        # depth but NOT the profile, so a metre-valued profile on a millimetre model is 1000x too
        # small. `_rect_profile` also sets a Position, without which web-ifc silently skips the
        # element and the proxy renders INVISIBLE — a proxy nobody can see is the same as none, and
        # nothing would report it.
        profile = _rect_profile(out, dx / scale, dy / scale)
        rep = ifcopenshell.api.run("geometry.add_profile_representation", out, context=body,
                                   profile=profile, depth=float(dz))
        ifcopenshell.api.run("geometry.assign_representation", out, product=proxy, representation=rep)
        ifcopenshell.api.run("spatial.assign_container", out, products=[proxy], relating_structure=st)
        pset = ifcopenshell.api.run("pset.add_pset", out, product=proxy, name=PROXY_PSET)
        ifcopenshell.api.run("pset.edit_pset", out, pset=pset, properties={
            "IsProxy": True,
            "ReplacesClasses": ", ".join(sorted({e.is_a() for e in els})),
            "ReplacesElementCount": len(els),
            "Note": "coarse LOD stand-in — not authored geometry; do not measure, schedule or price",
        })
        rows.append({"storey": name or "(unassigned)", "elements": len(els), "proxied": True,
                     "bbox": {"min": [round(x0, 3), round(y0, 3), round(z0, 3)],
                              "max": [round(x1, 3), round(y1, 3), round(z1, 3)]}})
        written_any = True

    if not written_any:
        return {"status": STATUS_NO_GEOMETRY, "written": False, "path": None, "storeys": rows,
                "elements_replaced": 0,
                "reason": "no element of the requested classes could be meshed, so no proxy was "
                          "written — an empty file would read as a successful export"}

    out.write(out_path)
    return {
        "status": STATUS_OK, "written": True, "path": out_path,
        "storeys": rows,
        "storeys_proxied": sum(1 for r in rows if r["proxied"]),
        "elements_replaced": sum(r["elements"] for r in rows if r["proxied"]),
        "classes": sorted(target),
        "declares_itself": {"name_prefix": PROXY_NAME_PREFIX, "pset": PROXY_PSET},
        "note": "one coarse box per storey standing in for the listed classes. Every box declares "
                "itself as a proxy by name and by pset, because a stand-in mistaken for authored "
                "geometry would be measured, scheduled and priced.",
    }
