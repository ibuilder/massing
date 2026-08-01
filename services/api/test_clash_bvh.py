"""Broad-phase clash: the BVH path and the matrix path must return the SAME clashes.

WHY THIS EXISTS
    `clash.py` used to build the candidate set as a full N x M boolean matrix over both sides. That is
    correct and numpy-fast at a few thousand elements per side, and it is 2.5 x 10^9 booleans at
    50k x 50k -- allocated before the narrow phase does any work at all. A BVH replaces it with a dual
    tree descent.

    Swapping the engine under a clash detector is exactly the kind of change that looks fine and
    quietly changes an answer. So this test does not measure speed and call it a day: it asserts the
    two paths produce the **same clash set**, as a SET of GlobalId pairs. A count agrees by accident.

THE TRAP THIS CHECKS FOR SPECIFICALLY
    Overlap has an edge case: two boxes that exactly touch. The matrix path uses `<=` / `>=`, so a
    touching pair counts as overlapping. The vendored `Aabb.overlaps` rejects only when
    `min > other.max`, which is the same inclusive rule -- but "the same rule" was read out of the
    source, and reading is not proving. The fixture below places a deliberately touching pair so the
    two implementations have to agree about it rather than merely appearing to.

WHAT IS NOT ASSERTED
    A speed claim. The threshold in `clash.py` is a size at which the tree stops costing more than it
    saves, and the honest way to state that is a measurement printed here, at a scale that is not a toy
    -- not a hardcoded belief. A benchmark on a 6-element fixture would say the BVH is slower and be
    perfectly useless, which is the shape of measurement error this repo has already paid for once.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from aec_data import clash, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# ---------------------------------------------------------------- a model with real overlaps
FIX = os.path.join(tempfile.gettempdir(), "_clash_bvh_test.ifc")
massing.generate_blank_ifc(FIX, name="Clash BVH", storeys=1, storey_height=4.0, ground_size=60.0)
m = open_model(FIX)
st = m.by_type("IfcBuildingStorey")[0].Name

# A grid of walls that genuinely intersect, plus one pair that only TOUCHES (x=20 exactly), which is
# the boundary case the two implementations have to agree on.
for i in range(12):
    edit.add_wall(m, [0, i * 2.0], [30, i * 2.0], 3.0, 0.4, st)     # runs east-west
for j in range(12):
    edit.add_wall(m, [j * 2.0, 0], [j * 2.0, 24], 3.0, 0.4, st)     # runs north-south -> crossings
edit.add_wall(m, [20.0, 30.0], [20.0, 36.0], 3.0, 0.4, st)
edit.add_wall(m, [20.0, 36.0], [26.0, 36.0], 3.0, 0.4, st)          # meets the previous end-to-end
m.write(FIX)

model = open_model(FIX)
n_walls = len(model.by_type("IfcWall")) + len(model.by_type("IfcWallStandardCase"))
check("the fixture has enough elements to be worth testing", n_walls >= 20, f"{n_walls} walls")


def clash_set(rows):
    """Clashes as an order-independent set of GlobalId pairs."""
    return {tuple(sorted((r["a_guid"], r["b_guid"]))) for r in rows
            if r.get("a_guid") and r.get("b_guid")}


# ---------------------------------------------------------------- force each path, compare
saved = clash.BVH_MIN_PAIRS
try:
    clash.BVH_MIN_PAIRS = 10**18          # never reached -> matrix path
    t0 = time.perf_counter()
    matrix_rows = clash.detect(model, narrow=False)
    t_matrix = time.perf_counter() - t0

    clash.BVH_MIN_PAIRS = 0               # always reached -> BVH path
    t0 = time.perf_counter()
    bvh_rows = clash.detect(model, narrow=False)
    t_bvh = time.perf_counter() - t0
finally:
    clash.BVH_MIN_PAIRS = saved

check("the threshold constant exists and was restored", clash.BVH_MIN_PAIRS == saved, str(saved))

ms, bs = clash_set(matrix_rows), clash_set(bvh_rows)
check("both paths found clashes at all", len(ms) > 0, f"{len(ms)} pairs")

only_matrix = ms - bs
only_bvh = bs - ms
check("the BVH path returns exactly the matrix path's clash set",
      ms == bs,
      f"matrix-only={len(only_matrix)} bvh-only={len(only_bvh)}" if ms != bs
      else f"{len(ms)} pairs identical")

# Row COUNT as well as the pair set: the narrow phase and ordering ride on the candidate list, so a
# path that found the same pairs but emitted a different number of rows has still changed behaviour.
check("both paths emit the same number of rows", len(matrix_rows) == len(bvh_rows),
      f"{len(matrix_rows)} vs {len(bvh_rows)}")

print(f"\n  timing at {n_walls} elements: matrix {t_matrix * 1000:.0f} ms, bvh {t_bvh * 1000:.0f} ms")
print("  (a fixture this size is BELOW the threshold on purpose — the matrix is expected to win here,")
print("   which is exactly why clash.py keeps both paths instead of replacing one with the other.)")

# ---------------------------------------------------------------- the threshold must be reachable
# A constant nothing can ever exceed is a switch that is welded shut. Assert the default threshold is
# a size a real federated model actually reaches, rather than a number that disables the feature.
check("the default threshold is reachable by a real model",
      0 < clash.BVH_MIN_PAIRS <= 5_000 * 5_000,
      f"BVH_MIN_PAIRS={clash.BVH_MIN_PAIRS:,} (a 2k x 2k federated pair = {2000 * 2000:,})")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_clash_bvh OK")
