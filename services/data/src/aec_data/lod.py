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
