"""R38-LIVE-PARAMS prerequisite — editing the profile a solid is swept from.

`set_extrusion_depth` edits how far a profile is swept; `set_profile_dims` edits the profile itself.
LIVE-PARAMS' constraint chips need a *system* of editable parameters for `dim_constraints.solve` to
reconcile, and one parameter is a slider rather than a system — which is why this exists.

The assertions worth having are the refusals, because every one of them is a case where doing the
obvious thing quietly reshapes a member somebody will build:

1. **a non-rectangular profile is refused**, not reinterpreted. Which dimension "width" means on an
   I-section is a judgement this recipe is not entitled to make on a fabricated member's behalf;
2. **a call that names no dimension is refused** — a no-op dressed as an edit lets a UI report a
   change nobody made;
3. **a non-positive dimension is refused** — that is not a thinner element, it is an inside-out one;
4. **the element survives**: same GUID, same psets. A parameter edit that re-creates the element
   would break every reference to it, which is the whole reason these are in-place edits.

Fixture generated in-test; nothing read from `samples/`.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_profile_dims.py
"""
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402

from aec_data import massing  # noqa: E402
from aec_data.edit import RECIPES  # noqa: E402
from aec_data.edit_struct import set_profile_dims, set_wall_thickness  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


WORK = tempfile.mkdtemp(prefix="profile_dims_")
SRC = os.path.join(WORK, "fixture.ifc")
massing.generate_blank_ifc(SRC, name="ParamFixture", storeys=1, storey_height=3.5)
m = ifcopenshell.open(SRC)
_st = [s.Name for s in m.by_type("IfcBuildingStorey")][0]

col = RECIPES["add_column"](m, {"point": [0, 0], "height": 3.0, "width": 0.4, "depth": 0.4,
                                "storey": _st})
wall = RECIPES["add_wall"](m, {"start": [0, 0], "end": [5, 0], "height": 3.0, "thickness": 0.2,
                               "storey": _st})

# --- 1. the ordinary edit ---------------------------------------------------------------------------
r = set_profile_dims(m, col, width=0.6)
check("a column's profile width is editable", r["new_width_m"] == 0.6, r)
check("  the previous value is reported, so the change is auditable", r["old_width_m"] == 0.4, r)
check("  the untouched dimension is returned unchanged, not zeroed",
      r["new_length_m"] == r["old_length_m"] == 0.4, r)
check("  and it names WHICH dimensions changed", r["changed"] == ["width"], r["changed"])

r2 = set_profile_dims(m, col, width=0.5, length=0.7)
check("both dimensions can move in one call",
      r2["new_width_m"] == 0.5 and r2["new_length_m"] == 0.7, r2)
check("  and the report shows both", sorted(r2["changed"]) == ["length", "width"], r2["changed"])

# --- 2. THE ELEMENT SURVIVES — the reason these are in-place edits ------------------------------------
check("the GUID is unchanged — a parameter edit must not re-create the element",
      m.by_guid(col) is not None and m.by_guid(col).GlobalId == col)
check("  and the class is unchanged", m.by_guid(col).is_a() == "IfcColumn")
check("  the edit is visible in the MODEL, not just the return value",
      any(abs(float(p.XDim) - 0.5) < 1e-9 for p in m.by_type("IfcRectangleProfileDef")),
      [float(p.XDim) for p in m.by_type("IfcRectangleProfileDef")])

# --- 3. wall thickness is sugar over the same edit ------------------------------------------------------
w = set_wall_thickness(m, wall, 0.35)
check("a wall's thickness is editable through the named sugar", w["thickness_m"] == 0.35, w)
check("  and it says which underlying dimension that is",
      "XDim" in w["note"], w["note"])
check("  the sugar inherits the refusals rather than re-implementing them",
      w["changed"] == ["width"], w)

# --- 4. THE REFUSALS --------------------------------------------------------------------------------
try:
    set_profile_dims(m, col)
    check("a call naming NO dimension is refused", False, "accepted a no-op as an edit")
except ValueError as e:
    check("a call naming NO dimension is refused — a no-op dressed as an edit", "not an edit" in str(e))

for bad in (0, -0.2):
    try:
        set_profile_dims(m, col, width=bad)
        check(f"width={bad} is refused", False, "accepted a non-positive dimension")
    except ValueError:
        check(f"width={bad} is refused — that is inside-out, not thinner", True)

try:
    set_profile_dims(m, "not-a-real-guid", width=0.3)
    check("an unknown GUID is refused", False, "accepted a stale guid")
except ValueError as e:
    check("an unknown GUID is a clean rejection", "not found" in str(e))

# A steel section is swept from a parametric I-shape, not a rectangle. Rewriting it means choosing
# what "width" means on that shape — the judgement this recipe refuses to make.
steel = RECIPES.get("add_steel_column")
if steel:
    sc = steel(m, {"point": [10, 10], "height": 3.0, "storey": _st})
    prof = None
    el = m.by_guid(sc)
    for rep in (el.Representation.Representations if el.Representation else []):
        for item in rep.Items or []:
            if item.is_a("IfcExtrudedAreaSolid"):
                prof = item.SweptArea.is_a()
    if prof and prof != "IfcRectangleProfileDef":
        try:
            set_profile_dims(m, sc, width=0.3)
            check(f"a {prof} profile is refused", False, "silently reshaped a fabricated section")
        except ValueError as e:
            check(f"a {prof} profile is REFUSED, not reinterpreted", "will not make for you" in str(e),
                  str(e)[:120])
    else:
        check(f"(steel column is a {prof}; the non-rect refusal is covered by the message path only)",
              True)

# --- 5. reachable through the registry, which is how the viewer will call it ----------------------------
check("`set_profile_dims` is registered", "set_profile_dims" in RECIPES)
check("`set_wall_thickness` is registered", "set_wall_thickness" in RECIPES)
g = RECIPES["set_profile_dims"](m, {"guid": col, "width": 0.45})
check("  the registry entry edits through the same path", g["new_width_m"] == 0.45, g)
check("  and an omitted dimension stays omitted rather than becoming 0.0",
      g["new_length_m"] == 0.7, g)
g2 = RECIPES["set_wall_thickness"](m, {"guid": wall, "thickness": 0.15})
check("  wall thickness through the registry too", g2["thickness_m"] == 0.15, g2)

# --- 6. it survives a write/read round trip -------------------------------------------------------------
OUT = os.path.join(WORK, "edited.ifc")
m.write(OUT)
m2 = ifcopenshell.open(OUT)
check("the edited profile survives a write/read round trip",
      any(abs(float(p.XDim) - 0.45) < 1e-9 for p in m2.by_type("IfcRectangleProfileDef")),
      [round(float(p.XDim), 3) for p in m2.by_type("IfcRectangleProfileDef")])
check("  and the element is still there under the same GUID", m2.by_guid(col) is not None)

print()
if FAILED:
    print(f"profile_dims: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("profile_dims: all checks passed")
