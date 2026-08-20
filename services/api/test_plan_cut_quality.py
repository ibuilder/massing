"""R43-PLAN-EMPTY-AT-CUT ②③ — a plan that misses the storey must say so, not print blank.

THE DEFECT, measured on `samples/basichouse.ifc` before this landed: storey "Floor 1" at 2.400 m,
default cut 1.200 m, so the plane sits at 3.600 m while the whole model tops out at 2.42 m.

      elements the plane passes through:   2
      elements standing on that storey:   16
      best available cut on that storey:   6 elements, at 2.500 m

Two loops is truthy, so the `if not polys` guard from ① never fired. The sheet composed in full —
titleblock, general notes, graphic scale, north arrow, "CUT PLANE 3.60 m AFF" — around two stray
slivers, and said nothing. **A drawing that looks finished and carries no building is worse than an
obviously empty one**, because it is the one that gets issued.

WHY A BOOLEAN COULD NOT CATCH IT. `not polys` tests for zero; the failure is *nearly* zero. Same
shape as every threshold here that was looser than the failure it guarded. The fix measures the
chosen cut against the best cut available on the storey — a fraction cannot be fooled by two loops.

WHAT IS DELIBERATELY NOT DONE. No silent re-cut. The titleblock prints the cut elevation, so moving
the plane and staying quiet would make that printed number a lie — a confident wrong answer instead
of a visible missing one. It names the better height and leaves the choice to a person.

FIXTURES ARE BUILT, NOT BORROWED. This file first read `samples/basichouse.ifc`, which exists on a
dev box and is **not tracked**: `git ls-files samples/` returns three files against ten `.ifc` on
disk. It passed locally and failed on CI with FileNotFoundError — the exact shape recorded in the
"test fixtures must be in the archive" lesson, and a reminder that a green local run is a claim
about a local tree. Geometry is synthesised here (`_boxes`) or generated with
`massing.generate_blank_ifc`, the way `test_sections.py` does it, so the suite carries its own
inputs. The numbers above are kept because they are the real measurement that motivated the fix.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_plan_cut_quality.py
"""
import os
import re
import sys

_DATA_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import trimesh  # noqa: E402

from aec_data import drawings, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _boxes(spec):
    """`[(z_lo, z_hi, n), ...]` -> baked-mesh triples, the shape `bake()` returns.

    Only the vertical extent matters to the rule under test, so the footprint is a fixed slab
    offset per element to keep the linework distinguishable.
    """
    out = []
    for i, (lo, hi, n) in enumerate(spec):
        for k in range(n):
            b = trimesh.creation.box(extents=(4.0, 0.3, max(hi - lo, 0.01)))
            b.apply_translation((k * 5.0, i * 5.0, (lo + hi) / 2.0))
            out.append((f"GUID{i}_{k}", "IfcWall", b))
    return out


# A storey at 0.0 whose 12 walls stop at 2.4 m — the default 1.2 m cut passes through all of them.
HEALTHY = _boxes([(0.0, 2.4, 12)])

# The upper storey at 2.4 m reproduces the basichouse shape: most of its content is SHORT (stops at
# 2.8 m) and a couple of stubs run tall. The default cut lands at 3.6 m and catches only the stubs;
# a plane at 2.5 m would catch everything. 2 of 8 is the ratio the real model showed as 2 of 6.
GRAZING = HEALTHY + _boxes([(2.3, 2.8, 6), (2.3, 3.9, 2)])

# A location's own `add_header`-style early return: with no polys AND no grid, `plan_drawing_svg`
# returns a stub rather than composing a sheet, so the banner has nowhere to appear. The dangerous
# case is the one that DOES compose — a full titleblock around nothing — so the empty test supplies
# a grid, which is what a real project always has.
GRID = {"x": [(0.0, "1"), (10.0, "2")], "y": [(0.0, "A"), (10.0, "B")]}


def attrs(svg):
    def one(name, cast=int):
        m = re.search(rf'data-plan-cut-{name}="([\d.]+)"', svg)
        return cast(m.group(1)) if m else None
    return {"spans": one("spans"), "best": one("best"), "best_z": one("best-z", float)}


# --- the regression case: a grazing cut, which ① could not see -----------------------------------
q_bad = drawings.cut_plane_quality(GRAZING, 2.4, 1.2)
svg_bad = drawings.plan_drawing_svg(GRAZING, 2.4, 1.2, "Upper")

check("a cut that grazes the storey is reported, though it drew SOME linework",
      "THIS CUT MISSES MOST OF THE STOREY" in svg_bad,
      f"spans={q_bad['at_cut']} best={q_bad['best']} ratio={q_bad['ratio']:.2f}")
check("and it drew some linework, so ①'s `if not polys` genuinely could not have caught it",
      q_bad["at_cut"] > 0,
      f"{q_bad['at_cut']} element(s) at the cut - truthy, hence invisible to a boolean")

# --- the suggestion must be REAL: acting on it has to actually improve the drawing ---------------
better = drawings.cut_plane_quality(GRAZING, 2.4, q_bad["best_z"] - 2.4)
check("the suggested cut height, applied, passes through strictly more elements",
      better["at_cut"] > q_bad["at_cut"],
      f"at 3.600 m -> {q_bad['at_cut']}; at {q_bad['best_z']:.3f} m -> {better['at_cut']}")
check("and the sheet prints that height, so the reader can act on it",
      f"{q_bad['best_z']:.3f} m" in svg_bad)

# --- no false positive on a plan that is fine ----------------------------------------------------
q_ok = drawings.cut_plane_quality(HEALTHY, 0.0, 1.2)
svg_ok = drawings.plan_drawing_svg(HEALTHY, 0.0, 1.2, "Ground")
check("a representative cut is NOT warned about",
      "MISSES MOST OF THE STOREY" not in svg_ok and "NO GEOMETRY AT THIS CUT" not in svg_ok,
      f"spans={q_ok['at_cut']} best={q_ok['best']} ratio={q_ok['ratio']:.2f}")

# --- the truly-empty case still reads as empty, not as 'misses most' -----------------------------
svg_empty = drawings.plan_drawing_svg(HEALTHY, 20.0, 1.2, "Sky", GRID)
check("a cut with nothing at all says NO GEOMETRY - a different fact from a badly-placed cut",
      "NO GEOMETRY AT THIS CUT" in svg_empty and "MISSES MOST" not in svg_empty)

# --- header data and banner must agree: one measurement, two consumers ---------------------------
a = attrs(svg_bad)
check("the published data matches the measurement the banner used - no second, drifting sweep",
      a["spans"] == q_bad["at_cut"] and a["best"] == q_bad["best"]
      and abs(a["best_z"] - q_bad["best_z"]) < 1e-6,
      f"header={a} measured={q_bad}")

# --- 'unmeasurable' must not render as 'zero' ----------------------------------------------------
empty_q = drawings.cut_plane_quality([], 0.0, 1.2)
check("with nothing to cut at any height, ratio is None rather than 0.0",
      empty_q["ratio"] is None and empty_q["best"] == 0, str(empty_q))

check("the warning is conditional, not unconditional",
      ("MISSES MOST OF THE STOREY" in svg_bad) and ("MISSES MOST OF THE STOREY" not in svg_ok))

# --- ③ the level list carries a cut height a caller can act on ------------------------------------
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_plan_cut_quality.ifc")
massing.generate_blank_ifc(TMP, name="Cut Quality", storeys=3, storey_height=3.0, ground_size=20.0)
levels = drawings.storeys_with_cut(open_model(TMP))

check("the level list still carries what every existing caller reads",
      bool(levels) and all({"name", "elevation", "guid"} <= set(x) for x in levels),
      "additive only - name/elevation/guid unchanged")
check("every level carries a usable cut height and both span counts",
      bool(levels) and all(x.get("cut_height", 0) > 0 and "cut_default_spans" in x
                           and "cut_best_spans" in x for x in levels),
      "; ".join(f"{x['name']}={x['cut_height']}" for x in levels))
check("a storey the default already serves KEEPS the 1.2 m convention",
      any(x["cut_height"] == drawings.DEFAULT_CUT_M for x in levels),
      "maximising element count proposed 0.400 m on a healthy floor - below every door and window; "
      "the convention earns its default")

# The override rule must be the SAME rule the banner uses, or a level can be offered a height the
# sheet never said it needed. Driven directly rather than inferred from one model's happenstance.
for label, meshes, elev in (("grazing", GRAZING, 2.4), ("healthy", HEALTHY, 0.0)):
    q = drawings.cut_plane_quality(meshes, elev, drawings.DEFAULT_CUT_M)
    unrep = q["ratio"] is not None and q["best"] >= 4 and q["ratio"] < 0.5
    warned = "MISSES MOST OF THE STOREY" in drawings.plan_drawing_svg(
        meshes, elev, drawings.DEFAULT_CUT_M, label)
    check(f"override condition and banner condition agree on the {label} storey - one rule",
          unrep == warned, f"unrepresentative={unrep} banner={warned}")

try:
    os.remove(TMP)
except OSError:
    pass

print()
if FAILED:
    print(f"FAILED: {'; '.join(FAILED)}")
    sys.exit(1)
print("plan cut quality OK - a grazing cut is named, the suggested height is verified to be better, "
      "a good plan is left alone, an empty storey stays a distinct fact, and the level list's "
      "override fires on exactly the condition the sheet warns on")
