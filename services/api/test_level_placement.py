"""LEVEL-PLACE — a placement with no storey lands on the GROUND FLOOR, and that is not a neutral default.

`edit_core._first_storey(model, None)` returns `sts[0]` — the lowest storey by elevation.
`edit.place_type` then containers the occurrence there AND sets its Z to that storey's elevation. So
every authoring call that omits `storey` places on the ground floor, at Z=0, whatever level the user
is working on.

**Two of the three authoring paths always handled this; the library palette did not.**

  * draw-in-3D — `apps/web/src/viewer/app.ts` `finishDraft()`:
        if (activeStorey && params.storey === undefined) params.storey = activeStorey;
  * the AI planner — `services/api/src/aec_api/nl_ai.py` `_fill_context()` injects `active_storey`
    server-side into any recipe whose spec declares a `storey`, covering the LLM and keyword paths
    identically.
  * the library palette — `apps/web/src/viewer/tools/contentLibrarySection.ts` and the
    "⊕ Place selected family" button in `apps/web/src/viewer/tools/authoringSection.ts` — sent none.

**Why nothing caught it.** `services/api/test_content.py` places content on a model built with
`generate_blank_ifc(..., storeys=1)`, and always passes a storey explicitly. On a one-storey model
"the lowest storey" and "the right storey" are the same entity, so the defect is invisible **by
construction of the fixture**, not by oversight in the assertions. `test_family_library.py` does not
mention a storey at all. That is the lesson worth keeping: *a fixture with one of something cannot
test which one was chosen.* Everything below therefore builds a THREE-storey model.

This asserts the ENGINE's contract — where an element actually ends up — not that a parameter is
threaded. A wiring-only test passes on a `storey` that is forwarded and then ignored, which is the
failure shape this repository has hit repeatedly: the check aimed one layer above the behaviour.

Run: PYTHONPATH=src ./.venv/bin/python test_level_placement.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "src")))

import ifcopenshell
import ifcopenshell.util.element as ue

from aec_data import edit, families, massing

TMP = os.path.join(tempfile.mkdtemp(prefix="levelplace_"), "three_storey.ifc")
massing.generate_blank_ifc(TMP, name="Level Placement", storeys=3, storey_height=4.0, ground_size=40.0)
model = ifcopenshell.open(TMP)

storeys = sorted(model.by_type("IfcBuildingStorey"), key=lambda s: float(getattr(s, "Elevation", 0) or 0))
assert len(storeys) == 3, f"the fixture must be MULTI-storey or it cannot tell one from another: {storeys}"
ground, top = storeys[0], storeys[-1]
ground_z = float(getattr(ground, "Elevation", 0) or 0)
top_z = float(getattr(top, "Elevation", 0) or 0)
assert top_z > ground_z, (top_z, ground_z)


def placed(guid):
    """(containing storey name, placement Z) for a GUID — where the element ACTUALLY ended up."""
    el = next((e for e in model.by_type("IfcProduct") if e.GlobalId == guid), None)
    assert el is not None, f"no element with GUID {guid!r}"
    container = ue.get_container(el)
    coords = el.ObjectPlacement.RelativePlacement.Location.Coordinates if el.ObjectPlacement else None
    return (container.Name if container else None), (float(coords[2]) if coords else None)


# ---- 1. a family: named storey vs omitted -------------------------------------------------------
g_named = families.add_family(model, "steel_column", top.Name, [7.0, 5.0])
name, z = placed(g_named)
assert name == top.Name and z == top_z, (
    f"a family placed with storey={top.Name!r} must land THERE, got {name!r} at Z={z}. This is the "
    "contract the fix depends on — if it were false, threading the storey through the UI would "
    "change nothing and the test below would be measuring the wrong thing.")

g_bare = families.add_family(model, "steel_column", None, [5.0, 5.0])
bare_name, bare_z = placed(g_bare)
assert bare_name == ground.Name and bare_z == ground_z, (
    f"expected the documented ground-floor fallback, got {bare_name!r} at Z={bare_z}")
assert bare_name != name, (
    "the omitted-storey placement must differ from the named one, or this file proves nothing: it "
    "would pass identically on a single-storey model, which is exactly how this defect survived.")

# ---- 2. content: the same fallback, through a different recipe ----------------------------------
r_named = edit.place_content(model, "desk", [11.0, 5.0], storey=top.Name)
c_name, c_z = placed(r_named["guid"])
assert c_name == top.Name and c_z == top_z, (c_name, c_z)

r_bare = edit.place_content(model, "desk", [9.0, 5.0])
cb_name, cb_z = placed(r_bare["guid"])
assert cb_name == ground.Name and cb_z == ground_z, (cb_name, cb_z)

# ---- 3. a MIDDLE storey, because "top" and "the last one in the list" are not the same claim -----
# `_first_storey` scans in elevation order and returns `sts[0]` when the name misses. Naming only the
# top storey cannot distinguish "found Level 3" from "fell through to the end of the list", and a
# fallback that happened to pick the LAST entry would pass every assertion above.
middle = storeys[1]
g_mid = families.add_family(model, "steel_column", middle.Name, [3.0, 5.0])
m_name, m_z = placed(g_mid)
assert m_name == middle.Name and m_z == float(getattr(middle, "Elevation", 0) or 0), (m_name, m_z)

# ---- 4. an unknown storey name falls back rather than raising ------------------------------------
# Worth pinning: the UI sends a NAME, and storeys are renameable. If a stale name raised, changing a
# level name would break placement instead of degrading it.
g_unknown = families.add_family(model, "steel_column", "No Such Level", [1.0, 5.0])
u_name, _ = placed(g_unknown)
assert u_name == ground.Name, f"an unknown storey name must fall back, got {u_name!r}"

print(f"LEVEL-PLACE OK - 3 storeys ({ground.Name} @ {ground_z}, {middle.Name}, {top.Name} @ {top_z}). "
      "A family and a content item each land on the storey they NAME, and each fall to the ground "
      "floor when none is given — the fallback the library palette was hitting on every placement. "
      "A middle storey is asserted separately so 'found it' cannot be confused with 'ran off the end "
      "of the list', and an unknown name is asserted to DEGRADE rather than raise, because the UI "
      "sends a name and levels can be renamed. The fixture is deliberately multi-storey: the existing "
      "content tests build one storey, where the wrong answer and the right one are the same entity.")
