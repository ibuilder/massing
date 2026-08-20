"""R43-PLAN-EMPTY-AT-CUT ② — a plan that misses the storey must say so, not print blank.

THE DEFECT. The guard added in ① asked `if not polys` — did the cut plane find **exactly** nothing.
That is the rare case. The common one is a plane that *grazes* the top of the geometry:

    samples/basichouse.ifc, storey "Floor 1" at 2.400 m, default cut 1.200 m -> plane at 3.600 m
      elements the plane passes through:   2
      elements standing on that storey:   16
      best available cut on that storey:   6 elements, at 2.500 m

Two loops is truthy, so the banner never fired. The sheet composed in full — titleblock, general
notes, graphic scale, north arrow, "CUT PLANE 3.60 m AFF" — around two stray slivers, and said
nothing. **A drawing that looks finished and carries no building is worse than an obviously empty
one**, because it is the one that gets issued.

WHY A BOOLEAN COULD NOT CATCH IT. `not polys` is a test for zero; the failure is *nearly* zero.
The same shape as every threshold in this repo that was looser than the failure it guarded. The fix
is to measure the chosen cut against the best cut available on the storey — a fraction cannot be
fooled by two loops the way a boolean is.

WHAT IS DELIBERATELY NOT DONE. The plan does not silently re-cut at the better height. The
titleblock prints the cut elevation, so moving the plane and staying quiet would make that printed
number a lie — a confident wrong answer instead of a visible missing one. It names the better height
and leaves the choice to a person.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_plan_cut_quality.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "src"))

import ifcopenshell  # noqa: E402

from aec_data import drawings  # noqa: E402

FAILED = []
SAMPLES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "samples")


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def attrs(svg):
    """The measurement the header publishes, as numbers."""
    def one(name, cast=int):
        m = re.search(rf'data-plan-cut-{name}="([\d.]+)"', svg)
        return cast(m.group(1)) if m else None
    return {"spans": one("spans"), "best": one("best"), "best_z": one("best-z", float)}


house = ifcopenshell.open(os.path.join(SAMPLES, "basichouse.ifc"))
meshes = drawings.bake(house)

# --- the regression case: a grazing cut, which ① could not see -----------------------------------
GRAZING_STOREY = 2.400
svg_bad = drawings.plan_svg(house, GRAZING_STOREY, title="Floor 1")
q_bad = drawings.cut_plane_quality(meshes, GRAZING_STOREY, 1.2)

check("a cut that grazes the storey is reported, though it drew SOME linework",
      "THIS CUT MISSES MOST OF THE STOREY" in svg_bad,
      f"spans={q_bad['at_cut']} best={q_bad['best']} ratio={q_bad['ratio']:.2f}")
check("and it drew some linework, so ①'s `if not polys` genuinely could not have caught it",
      q_bad["at_cut"] > 0, f"{q_bad['at_cut']} element(s) at the cut — truthy, hence invisible to a boolean")

# --- the suggestion must be REAL: acting on it has to actually improve the drawing ----------------
# Without this the banner could name any number and still read as helpful.
better = drawings.cut_plane_quality(meshes, GRAZING_STOREY, q_bad["best_z"] - GRAZING_STOREY)
check("the suggested cut height, applied, passes through strictly more elements",
      better["at_cut"] > q_bad["at_cut"],
      f"at {GRAZING_STOREY + 1.2:.3f} m -> {q_bad['at_cut']}; at {q_bad['best_z']:.3f} m -> {better['at_cut']}")
check("and the sheet prints that height, so the reader can act on it",
      f"{q_bad['best_z']:.3f} m" in svg_bad)

# --- no false positive on a plan that is fine ----------------------------------------------------
svg_ok = drawings.plan_svg(house, 0.0, title="Floor 0")
q_ok = drawings.cut_plane_quality(meshes, 0.0, 1.2)
check("a representative cut is NOT warned about",
      "MISSES MOST OF THE STOREY" not in svg_ok and "NO GEOMETRY AT THIS CUT" not in svg_ok,
      f"spans={q_ok['at_cut']} best={q_ok['best']} ratio={q_ok['ratio']:.2f}")

# --- the truly-empty case still reads as empty, not as 'misses most' -----------------------------
school = ifcopenshell.open(os.path.join(SAMPLES, "school_str.ifc"))
svg_empty = drawings.plan_svg(school, 11.400, title="Roof")
check("a cut with nothing at all still says NO GEOMETRY, a different fact from a bad cut",
      "NO GEOMETRY AT THIS CUT" in svg_empty and "MISSES MOST" not in svg_empty)

# --- header data and banner must agree: one measurement, two consumers ---------------------------
a = attrs(svg_bad)
check("the published data matches the measurement the banner used — no second, drifting sweep",
      a["spans"] == q_bad["at_cut"] and a["best"] == q_bad["best"]
      and abs(a["best_z"] - q_bad["best_z"]) < 1e-6,
      f"header={a} measured={q_bad}")

# --- the rule must be able to say 'this storey is genuinely empty' -------------------------------
# ratio is None (not 0.0) when nothing can be cut at ANY height — 'unmeasurable' must not render as
# 'zero', the distinction this repo keeps relearning.
empty_q = drawings.cut_plane_quality([], 0.0, 1.2)
check("with nothing to cut at any height, ratio is None rather than 0.0",
      empty_q["ratio"] is None and empty_q["best"] == 0, str(empty_q))

# --- mutation check: the rule must be capable of going red ---------------------------------------
# Feed it a storey whose cut is perfect and confirm `unrepresentative` would be False, so the
# assertion above is not passing because the banner is always emitted.
check("the warning is conditional, not unconditional",
      ("MISSES MOST OF THE STOREY" in svg_bad) and ("MISSES MOST OF THE STOREY" not in svg_ok))

print()
if FAILED:
    print(f"FAILED: {'; '.join(FAILED)}")
    sys.exit(1)
print("plan cut quality OK — a grazing cut is named, the suggested height is verified to be better, "
      "a good plan is left alone, and an empty storey stays a distinct fact")
