"""IFCPATCH-LIB (R15) — one-click IFC maintenance recipes.

The clean-the-model half of authoring: deterministic passes that remove dead data an IFC accumulates
over its life. v1 ships the two safe, unambiguous purges (nothing that touches element geometry or
GUIDs, so pins / RFIs / clashes keyed by GlobalId survive):

  * ``purge_orphan_psets``  — remove ``IfcPropertySet`` not attached to any element or type
    (no ``IfcRelDefinesByProperties`` points at it AND no ``IfcTypeObject.HasPropertySets`` lists it).
    The owned ``IfcProperty`` values go with it (``remove_deep2``).
  * ``purge_empty_groups``  — remove a plain ``IfcGroup`` with no members (no ``IfcRelAssignsToGroup``
    assigns anything to it). Restricted to the exact ``IfcGroup`` type — never systems / zones /
    building-systems, which are meaningful even when sparsely populated.

``scan(model)`` reports what each recipe WOULD remove (a dry run) so the UI can show the count before
anything is written. The recipes are registered in ``edit.RECIPES`` so they ride the existing
GUID-stable apply→republish pipeline.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as _ue


def _orphan_psets(model: ifcopenshell.file) -> list:
    """IfcPropertySets attached to nothing (element rel OR type list)."""
    used: set[int] = set()
    for r in model.by_type("IfcRelDefinesByProperties"):
        pd = getattr(r, "RelatingPropertyDefinition", None)
        if pd is not None:
            used.add(pd.id())
    for t in model.by_type("IfcTypeObject"):
        for ps in (getattr(t, "HasPropertySets", None) or []):
            used.add(ps.id())
    return [p for p in model.by_type("IfcPropertySet") if p.id() not in used]


def _empty_groups(model: ifcopenshell.file) -> list:
    """Plain IfcGroups (exact type) with no assigned members."""
    grouped: set[int] = set()
    for r in model.by_type("IfcRelAssignsToGroup"):
        g = getattr(r, "RelatingGroup", None)
        if g is not None and (r.RelatedObjects or []):
            grouped.add(g.id())
    return [g for g in model.by_type("IfcGroup") if g.is_a() == "IfcGroup" and g.id() not in grouped]


def purge_orphan_psets(model: ifcopenshell.file) -> int:
    """Remove every orphaned IfcPropertySet (+ its owned properties). Returns the count removed."""
    n = 0
    for ps in _orphan_psets(model):
        _ue.remove_deep2(model, ps)
        n += 1
    return n


def purge_empty_groups(model: ifcopenshell.file) -> int:
    """Remove every empty plain IfcGroup (+ its owning IfcRelDeclares/aggregation stubs). Returns count."""
    n = 0
    for g in _empty_groups(model):
        _ue.remove_deep2(model, g)
        n += 1
    return n


# recipe name → (label, mutator, detector).
#
# **This table is an ADVERTISEMENT, not just a definition, and the difference matters to a gate.**
# ``scan()`` builds one row per entry and hands it to the client; the maintenance tool renders a Purge
# button per row and POSTs ``row["recipe"]`` straight back to ``/edit``. So these recipes are dispatched
# by NAME AS DATA — the string never appears as a literal in any client file, and a reachability check
# that greps the tree for callers cannot see them. `services/api/test_recipe_reach.py` reads these keys
# for exactly that reason, and had listed both recipes as unreachable while the button shipped.
#
# The detector lives here so the advertisement cannot drift from the capability: ``scan()`` iterates
# this dict rather than naming the two recipes a second time, so a recipe added here is scanned,
# advertised and reachable in one edit — and one added WITHOUT a detector fails to construct rather
# than quietly going unadvertised.
RECIPES = {
    "purge_orphan_psets": ("Purge orphaned property sets", purge_orphan_psets, _orphan_psets),
    "purge_empty_groups": ("Purge empty groups", purge_empty_groups, _empty_groups),
}


def extract_subset(model: ifcopenshell.file, keep_guids: set[str]) -> dict[str, Any]:
    """SUBSET-EXPORT — prune the model **in place** to just the physical elements whose ``GlobalId`` is
    in ``keep_guids`` (a discipline / selector slice you hand a consultant as a standalone IFC).

    Every ``IfcElement`` (wall/slab/column/door/MEP/…) NOT in the keep-set is removed with the
    ``root.remove_product`` API (which also detaches its spatial-containment / opening / property
    relationships and purges the owned geometry — ``remove_deep2`` alone can't, since a placed element
    has inverses). The **spatial skeleton** — ``IfcProject``, ``IfcSite``, ``IfcBuilding``,
    ``IfcBuildingStorey``, ``IfcSpace`` — and shared units / geometric contexts are left intact, so the
    pruned file is a valid IFC the kept elements are still correctly contained in, with GUIDs unchanged.
    Caller opens a throwaway copy of the source (never the live model) and writes the result. Returns
    ``{available, kept, removed}``."""
    import ifcopenshell.api.root  # local import — the api package is heavier than the util helpers

    keep = {g for g in keep_guids if g}
    elements = model.by_type("IfcElement")
    if not elements:
        return {"available": False, "kept": 0, "removed": 0,
                "message": "model has no IfcElement to subset"}
    removed = 0
    for e in list(elements):
        if getattr(e, "GlobalId", None) not in keep:
            ifcopenshell.api.root.remove_product(model, product=e)
            removed += 1
    return {"available": True, "kept": len(elements) - removed, "removed": removed}


def scan(model: ifcopenshell.file) -> dict[str, Any]:
    """Dry-run maintenance report — how many entities each recipe WOULD remove (no mutation)."""
    recipes = []
    for name, (label, _mutate, detect) in RECIPES.items():
        found = detect(model)
        recipes.append({
            "recipe": name, "label": label, "removable": len(found),
            "sample": [e.Name for e in found[:20] if getattr(e, "Name", None)],
        })
    return {"total_entities": len(list(model)),
            "cleanable": sum(r["removable"] for r in recipes),
            "recipes": recipes}


def scan_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return scan(open_model(ifc_path))

# --- IFCPATCH-LIB v2 (R15 carry-over): rebase / unit-convert / split ------------------------------
#
# Three transform recipes beyond the v1 purges. All GUID-stable (no element is created or destroyed),
# all deterministic, all reporting exactly what they touched.
#
# ``rebase_origin`` is the georeferencing-correct answer to "this model is a million metres from the
# origin": shift the *site* placement so the model draws near the scene origin, and push the same
# offset INTO the map conversion so the real-world coordinate of every element is unchanged. Moving
# geometry without fixing the georeference is the classic way to silently lose survey position.
#
# ``convert_length_unit`` changes the project length unit and rescales the length-valued data our
# authoring writes. The attribute whitelist below is explicit rather than schema-walked, so it is
# auditable — and the report names every entity type it touched plus anything it skipped, so a
# partially-convertible file can never masquerade as a fully-converted one.

_UNIT_SCALES = {                       # target name -> (IfcSIUnit Name, Prefix, metres per unit)
    "METRE": ("METRE", None, 1.0),
    "MILLIMETRE": ("METRE", "MILLI", 0.001),
    "CENTIMETRE": ("METRE", "CENTI", 0.01),
}

# entity type -> (linear attributes, areal attributes, volumetric attributes)
_LENGTH_ATTRS: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "IfcCartesianPoint": (("Coordinates",), (), ()),
    "IfcRectangleProfileDef": (("XDim", "YDim"), (), ()),
    "IfcCircleProfileDef": (("Radius",), (), ()),
    "IfcCircleHollowProfileDef": (("Radius", "WallThickness"), (), ()),
    "IfcIShapeProfileDef": (("OverallWidth", "OverallDepth", "WebThickness", "FlangeThickness"), (), ()),
    "IfcExtrudedAreaSolid": (("Depth",), (), ()),
    "IfcBuildingStorey": (("Elevation",), (), ()),
    "IfcSite": (("RefElevation",), (), ()),
    "IfcDoor": (("OverallHeight", "OverallWidth"), (), ()),
    "IfcWindow": (("OverallHeight", "OverallWidth"), (), ()),
    "IfcMaterialLayer": (("LayerThickness",), (), ()),
    "IfcQuantityLength": (("LengthValue",), (), ()),
    "IfcQuantityArea": ((), ("AreaValue",), ()),
    "IfcQuantityVolume": ((), (), ("VolumeValue",)),
}


def _map_conversion(model):
    convs = model.by_type("IfcMapConversion") if model.schema != "IFC2X3" else []
    return convs[0] if convs else None


def setup_facts(model: ifcopenshell.file) -> dict[str, Any]:
    """MODEL-SETUP — what a project's units and origin ARE, so the two repairs below can be offered
    honestly rather than as a guess.

    ``rebase_origin`` and ``convert_length_unit`` have been in the recipe registry, and reachable
    through ``POST /projects/{pid}/edit``, the whole time — `authoring_matrix.UNREACHED` lists both as
    "a capability no user can reach", which that file calls a defect rather than a gap. The reason a
    control could not simply be added is here: **nothing exposed the current state**. Offering
    "convert to millimetres" without saying what the units are now is a coin flip the user is asked
    to call, and a control whose state cannot be seen is the shape this codebase keeps repairing.

    So this reports what the repair needs to be *decided*, not merely what it would do:

    ``targets`` is sent BY THE SERVER rather than hardcoded in a client. The converter accepts three
    units and raises on anything else, so a dropdown that offered feet would render a 400. The same
    reason the maintenance scan sends recipe names as data.

    ``distance_from_origin`` is measured over the ROOT placements — exactly the set ``rebase_origin``
    shifts — so the number shown is the number the repair acts on, rather than a bounding box that
    happens to correlate with it.

    ``convertible`` is false when the file carries no ``LENGTHUNIT`` assignment, which is the one
    input that makes the converter raise rather than no-op.
    """
    import ifcopenshell.util.unit as uunit

    try:
        metres = float(uunit.calculate_unit_scale(model))
    except Exception:                                       # noqa: BLE001 — a file with no unit assignment
        metres = None
    named = [u for u in model.by_type("IfcNamedUnit")
             if getattr(u, "UnitType", None) == "LENGTHUNIT"]
    # Name the unit the way the CONVERTER names it when we can, so the current value and the target
    # list are drawn from one vocabulary; fall back to the file's own spelling when it is something
    # the converter does not model (a foot, an inch, a conversion-based unit).
    unit_name = None
    if metres is not None:
        for label, (_n, _p, m) in _UNIT_SCALES.items():
            if abs(metres - m) < 1e-12:
                unit_name = label
                break
    if unit_name is None and named:
        u = named[0]
        prefix = getattr(u, "Prefix", None)
        base = getattr(u, "Name", None)
        unit_name = f"{prefix}{base}" if prefix and base else (base or None)

    mc = _map_conversion(model)
    georeference = None
    if mc is not None:
        georeference = {
            "eastings": getattr(mc, "Eastings", None),
            "northings": getattr(mc, "Northings", None),
            "orthogonal_height": getattr(mc, "OrthogonalHeight", None),
        }

    # The root placements, and how far the furthest one sits from the file origin. A model authored
    # against a survey grid can sit millions of units out, which is what wrecks depth precision in a
    # renderer — the problem `rebase_origin` exists for.
    seen: set[int] = set()
    roots = 0
    furthest = 0.0
    for placement in model.by_type("IfcLocalPlacement"):
        if getattr(placement, "PlacementRelTo", None) is not None:
            continue
        rel = getattr(placement, "RelativePlacement", None)
        loc = getattr(rel, "Location", None) if rel is not None else None
        if loc is None or loc.id() in seen:
            continue
        seen.add(loc.id())
        roots += 1
        c = list(getattr(loc, "Coordinates", ()) or ()) + [0.0, 0.0, 0.0]
        furthest = max(furthest, (float(c[0]) ** 2 + float(c[1]) ** 2 + float(c[2]) ** 2) ** 0.5)

    return {
        "length_unit": unit_name,
        "length_unit_metres": metres,
        # `convertible` is the ENGINE's precondition restated, not a looser one: `bool(named)` alone
        # said yes to a foot-based file that `convert_length_unit` now refuses. The panel reads this
        # to decide whether to offer the control at all, so the two must agree — a control offered
        # for something the server will refuse is the "dropdown holding FOOT" failure one field down,
        # arriving through the SOURCE unit instead of the target.
        "convertible": bool(named) and all(u.is_a("IfcSIUnit") for u in named),
        "unconvertible_reason": (
            None if not named else
            None if all(u.is_a("IfcSIUnit") for u in named) else
            "conversion-based unit (e.g. feet) — this recipe rewrites SI assignments only"),
        "targets": sorted(_UNIT_SCALES),
        "georeference": georeference,
        "root_placements": roots,
        "distance_from_origin": furthest,
        "distance_from_origin_m": (furthest * metres) if metres is not None else None,
    }


def rebase_origin(model: ifcopenshell.file, point=(0.0, 0.0, 0.0)) -> dict[str, Any]:
    """Move the model so the given MODEL point becomes the origin, preserving real-world position.

    The shift lands on every **root** placement — an ``IfcLocalPlacement`` with no ``PlacementRelTo``
    — so anything placed relative to a root rides along and relative geometry is untouched. (A file
    whose spatial structure carries no placement chain, which is normal for authored-from-scratch
    models, is handled the same way: its element placements *are* the roots.) Storey ``Elevation``
    datums shift with the geometry so level and geometry never disagree. No element is created or
    destroyed, so every GlobalId survives.

    If the file carries an ``IfcMapConversion``, its Eastings / Northings / OrthogonalHeight absorb
    the same offset, so model coordinate → real coordinate still resolves to the same survey
    position (the georeferencing rule in the project brief). Returns what moved and whether the
    georeference followed.
    """
    import ifcopenshell.util.unit as uunit

    px, py, pz = (float(point[0]), float(point[1]), float(point[2] if len(point) > 2 else 0.0))
    if px == 0.0 and py == 0.0 and pz == 0.0:
        return {"offset": [0.0, 0.0, 0.0], "moved": False, "placements_shifted": 0,
                "storeys_rebased": 0, "georeference_updated": False,
                "note": "point is already the origin — nothing to do"}
    scale = uunit.calculate_unit_scale(model)              # metres per file unit
    dx, dy, dz = -px / scale, -py / scale, -pz / scale     # the shift, in FILE units

    seen: set[int] = set()
    shifted = 0
    for placement in model.by_type("IfcLocalPlacement"):
        if getattr(placement, "PlacementRelTo", None) is not None:
            continue                                        # rides its parent — shifting would double
        rel = getattr(placement, "RelativePlacement", None)
        loc = getattr(rel, "Location", None) if rel is not None else None
        if loc is None or loc.id() in seen:
            continue
        seen.add(loc.id())
        c = list(loc.Coordinates) + [0.0, 0.0, 0.0]
        loc.Coordinates = (c[0] + dx, c[1] + dy, c[2] + dz)
        shifted += 1
    storeys = 0
    for st in model.by_type("IfcBuildingStorey"):           # keep the level datum with the geometry
        if st.Elevation is not None:
            st.Elevation = float(st.Elevation) + dz
            storeys += 1
    if not shifted and not storeys:
        raise ValueError("nothing to rebase — this file has no root placements or storey datums")

    conv = _map_conversion(model)
    if conv is not None:                                   # push the offset into the georeference
        conv.Eastings = float(conv.Eastings or 0.0) + px
        conv.Northings = float(conv.Northings or 0.0) + py
        conv.OrthogonalHeight = float(conv.OrthogonalHeight or 0.0) + pz
    return {"offset": [-px, -py, -pz], "moved": True,
            "placements_shifted": shifted, "storeys_rebased": storeys,
            "georeference_updated": conv is not None,
            "note": ("real-world coordinates preserved via IfcMapConversion" if conv is not None
                     else "no IfcMapConversion in this file — model coordinates shifted, "
                          "no georeference to update")}


def convert_length_unit(model: ifcopenshell.file, to: str = "MILLIMETRE") -> dict[str, Any]:
    """Convert the project length unit, rescaling length data so real-world size is unchanged.

    Rescales the whitelisted length / area / volume attributes (see ``_LENGTH_ATTRS``) by the unit
    ratio (squared / cubed for areas / volumes), then rewrites the project's length unit. The report
    names every entity type touched and its count, so the conversion is auditable rather than a
    black box. Raises for an unknown target unit or a file with no length unit assignment.
    """
    import ifcopenshell.util.unit as uunit

    target = str(to or "").strip().upper()
    if target not in _UNIT_SCALES:
        raise ValueError(f"unknown target unit {to!r} — one of {sorted(_UNIT_SCALES)}")
    name, prefix, metres_per_target = _UNIT_SCALES[target]
    current = uunit.calculate_unit_scale(model)             # metres per current file unit
    ratio = current / metres_per_target                     # current units -> target units
    if abs(ratio - 1.0) < 1e-12:
        return {"from_scale": current, "to": target, "ratio": 1.0, "converted": {},
                "note": "already in the requested unit"}

    unit_entities = [u for u in model.by_type("IfcNamedUnit")
                     if getattr(u, "UnitType", None) == "LENGTHUNIT"]
    if not unit_entities:
        raise ValueError("no LENGTHUNIT assignment found in this file")

    # **REFUSE BEFORE MUTATING, not after.** Every target in `_UNIT_SCALES` is an `IfcSIUnit`
    # (metre with a prefix), and the rewrite below is guarded by `u.is_a("IfcSIUnit")` — so on a file
    # whose LENGTHUNIT is an `IfcConversionBasedUnit` (a foot, an inch: normal in a US survey model)
    # the rescale ran and the assignment did NOT change. The geometry moved, the declared unit did
    # not, and the report said *"unit assignment rewritten"*: a 10 ft wall came out 3.048 FEET, the
    # model silently 30.48% of its real size, with a success message. Reproduced before this guard
    # was written, not reasoned about.
    #
    # Refusing is the asymmetric choice. Refusing a convertible file costs the user one message;
    # converting an unconvertible one corrupts the model of record and says it worked. Replacing a
    # conversion-based unit with an SI one is a real feature — it has to rewrite the
    # `IfcUnitAssignment` and dispose of the `IfcMeasureWithUnit` behind it — and it is not this
    # change; the refusal names it rather than pretending the file is unsupported outright.
    unrewriteable = [u for u in unit_entities if not u.is_a("IfcSIUnit")]
    if unrewriteable:
        kinds = ", ".join(sorted({str(getattr(u, "Name", None) or u.is_a()) for u in unrewriteable}))
        raise ValueError(
            f"this file's length unit ({kinds}) is a conversion-based unit, which this recipe "
            "cannot rewrite — converting it would rescale the geometry and leave the declared unit "
            "unchanged. Nothing was changed.")

    converted: dict[str, int] = {}
    for cls, (lin, area, vol) in _LENGTH_ATTRS.items():
        try:
            entities = model.by_type(cls)
        except Exception:                                   # noqa: BLE001 — class absent from schema
            continue
        touched = 0
        for e in entities:
            for attrs, power in ((lin, 1), (area, 2), (vol, 3)):
                factor = ratio ** power
                for attr in attrs:
                    val = getattr(e, attr, None)
                    if val is None:
                        continue
                    if isinstance(val, (tuple, list)):
                        setattr(e, attr, tuple(float(v) * factor for v in val))
                    else:
                        setattr(e, attr, float(val) * factor)
                    touched += 1
        if touched:
            converted[cls] = touched

    for u in unit_entities:                                 # rewrite the unit assignment itself
        if u.is_a("IfcSIUnit"):
            u.Name = name
            u.Prefix = prefix
    return {"from_scale": current, "to": target, "ratio": ratio, "converted": converted,
            "entities_touched": sum(converted.values()),
            "note": "whitelisted length/area/volume attributes rescaled; unit assignment rewritten"}


def split_by_storey(model: ifcopenshell.file) -> dict[str, Any]:
    """Plan a per-storey split: ``{storey: [guids]}`` + the unassigned remainder.

    Pairs with ``extract_subset`` — hand one storey's GUID set to it against a throwaway copy and you
    have that storey as a standalone IFC. Reporting the plan separately keeps the destructive step
    explicit (and lets the UI show what each slice would contain before anything is written).
    """
    import ifcopenshell.util.element as ue

    by_storey: dict[str, list[str]] = {}
    unassigned: list[str] = []
    for el in model.by_type("IfcElement"):
        guid = getattr(el, "GlobalId", None)
        if not guid:
            continue
        try:
            container = ue.get_container(el)
        except Exception:                                   # noqa: BLE001
            container = None
        key = getattr(container, "Name", None) if container is not None else None
        if key:
            by_storey.setdefault(key, []).append(guid)
        else:
            unassigned.append(guid)
    return {"storeys": {k: sorted(v) for k, v in sorted(by_storey.items())},
            "counts": {k: len(v) for k, v in sorted(by_storey.items())},
            "unassigned": sorted(unassigned), "unassigned_count": len(unassigned),
            "note": "pass one storey's guids to extract_subset on a copy to write that slice"}
