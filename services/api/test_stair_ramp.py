"""R38-STAIR (server half) — a straight stair/ramp run, placed where it was drawn.

The recipes are easy. The assertion that matters is the refusal: **the geometry is never silently
reshaped to satisfy a limit.** A run too short for its rise produces a steep stair and SAYS so; it is
not quietly lengthened, because lengthening moves the top of the stair away from where the user drew
it — a change they cannot see and did not ask for. Same for a ramp steeper than 1:12.

So `within_limits` is a report, and these tests pin that it reports rather than enforces.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_stair_ramp.py
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402

from aec_data import massing  # noqa: E402
from aec_data.edit import RECIPES  # noqa: E402
from aec_data.edit_enclosure import (  # noqa: E402
    MAX_RAMP_SLOPE,
    MAX_RISER_M,
    MIN_TREAD_M,
    add_ramp,
    add_stair,
    ramp_geometry,
    stair_geometry,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 1. the geometry maths, testable without a model ------------------------------------------------
g = stair_geometry(rise=3.0, run=4.0)
check("a 3.0 m rise needs 16 risers at the 0.19 m maximum",
      g["riser_count"] == 16, g["riser_count"])
check("  the riser is derived, and lands under the maximum",
      g["riser"] <= MAX_RISER_M and abs(g["riser"] - 3.0 / 16) < 1e-6, g["riser"])
check("  the tread is the run divided by the same count",
      abs(g["tread"] - 4.0 / 16) < 1e-6, g["tread"])

# THE REFUSAL: 4.0 m of run over 16 treads is 0.25 m — exactly the minimum. Shorten it and the stair
# becomes non-compliant, and must SAY so rather than being silently lengthened.
tight = stair_geometry(rise=3.0, run=2.0)
check("a run too short for its rise is reported as OUTSIDE the limits",
      tight["within_limits"] is False, tight)
check("  and the reason says the stair stays where it was drawn",
      "placed where it was drawn" in tight["reason"], tight["reason"])
check("  and tells the user to lengthen the run rather than expect an adjustment",
      "lengthen the run" in tight["reason"], tight["reason"])
check("  the derived numbers are still returned — a refusal is not a blank",
      tight["riser_count"] > 0 and tight["tread"] is not None, tight)
check("a comfortable run IS reported as within limits",
      stair_geometry(rise=3.0, run=5.0)["within_limits"] is True)

for rise, run in ((0, 4.0), (3.0, 0), (-1, 4.0), (3.0, -2)):
    r = stair_geometry(rise=rise, run=run)
    check(f"stair_geometry({rise}, {run}) derives nothing rather than inventing a stair",
          r["within_limits"] is None and r["riser"] is None, r)

# --- 2. ramp slope is reported, not enforced ----------------------------------------------------------
ok_ramp = ramp_geometry(rise=0.5, run=6.0)
check("a 1:12 ramp is within the accessible limit", ok_ramp["within_limits"] is True, ok_ramp)
check("  and states the ratio in the form a reviewer reads",
      ok_ramp["slope_ratio"] == "1:12", ok_ramp["slope_ratio"])
steep = ramp_geometry(rise=1.0, run=6.0)
check("a 1:6 ramp is reported as too steep", steep["within_limits"] is False, steep)
check("  and is NOT silently lengthened", "placed where it was drawn" in steep["reason"],
      steep["reason"])
check("the limit itself is exposed, so the rule can be argued with",
      abs(MAX_RAMP_SLOPE - 1 / 12) < 1e-9 and MAX_RISER_M == 0.19 and MIN_TREAD_M == 0.25)
check("a zero-length ramp derives nothing", ramp_geometry(1.0, 0)["within_limits"] is None)

# --- 3. the recipes actually author IFC ----------------------------------------------------------------
import tempfile  # noqa: E402

path = tempfile.mktemp(suffix=".ifc")
massing.generate_blank_ifc(path, name="StairTest", storeys=2, storey_height=3.5)
m = ifcopenshell.open(path)
storeys = [s.Name for s in m.by_type("IfcBuildingStorey")]

sid = add_stair(m, (0, 0), (5, 0), width=1.2, storey=storeys[0], target_storey=storeys[1])
check("add_stair returns a GUID", isinstance(sid, str) and len(sid) == 22, sid)
check("  and creates an IfcStair", len(m.by_type("IfcStair")) == 1)
check("  with an aggregated IfcStairFlight — the flight is what carries the body",
      len(m.by_type("IfcStairFlight")) == 1)

rid = add_ramp(m, (0, 5), (12, 5), width=1.5, storey=storeys[0], target_storey=storeys[1])
check("add_ramp returns a GUID and creates IfcRamp + IfcRampFlight",
      isinstance(rid, str) and len(m.by_type("IfcRamp")) == 1 and len(m.by_type("IfcRampFlight")) == 1)
check("  the two GUIDs differ", sid != rid)
check("the stair is spatially contained, so it is in the storey a user can find it in",
      any(s.GlobalId == sid for r in m.by_type("IfcRelContainedInSpatialStructure")
          for s in r.RelatedElements))

for bad in ((0, 0), (0, 0)), ((1, 1), (1, 1)):
    try:
        add_stair(m, bad[0], bad[1], storey=storeys[0])
        check("zero-length run is refused", False, "accepted a degenerate run")
    except ValueError:
        check("a zero-length run raises rather than authoring a degenerate stair", True)
try:
    add_stair(m, (0, 0), (4, 0), width=0, storey=storeys[0])
    check("a non-positive width is refused", False, "accepted width=0")
except ValueError:
    check("a non-positive width raises rather than authoring a zero-width flight", True)

# --- 4. reachable through the recipe registry (how the web half will call it) ----------------------------
check("`add_stair` is registered as a recipe", "add_stair" in RECIPES)
check("`add_ramp` is registered as a recipe", "add_ramp" in RECIPES)
g2 = RECIPES["add_stair"](m, {"start": [0, 10], "end": [5, 10], "storey": storeys[0]})
check("  the registry entry authors through the same path",
      isinstance(g2, str) and len(m.by_type("IfcStair")) == 2, g2)
check("  and defaults width when the caller omits it",
      RECIPES["add_ramp"](m, {"start": [0, 15], "end": [12, 15]}) is not None)

print()
if FAILED:
    print(f"stair_ramp: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("stair_ramp: all checks passed")
