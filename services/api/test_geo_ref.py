"""
Georeferencing — where the building actually is.

CLAUDE.md has listed this as a watch-out from the start and nothing implemented it; the only
georeferencing code in the tree was inside ifcopenshell's own package. These tests pin the two
conversions that are easy to get wrong in ways that look right.
"""
import math
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data.geo import (  # noqa: E402
    METRES_PER_UNIT,
    degrees_to_dms,
    dms_to_degrees,
)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- the compound-angle trap ----------------------------------------------------------------------
# IFC stores lat/long as (deg, min, sec[, millionths]). Reading element 0 as the coordinate is an
# easy mistake that puts the building up to a degree — tens of kilometres — away, while returning a
# number that looks entirely reasonable.
check("degrees+minutes+seconds combine, not just the degrees",
      abs(dms_to_degrees((51, 30, 26)) - 51.507222) < 1e-5,
      f"got {dms_to_degrees((51, 30, 26))} for Greenwich-ish 51°30'26\"")
check("reading only the degrees would be wrong by minutes", dms_to_degrees((51, 30, 26)) != 51.0)

# The sign belongs to the WHOLE angle. Negating only the degrees moves a southern site north of
# where it should be by the minutes-and-seconds part.
sydney = dms_to_degrees((-33, -52, -4))
check("a southern latitude stays south", sydney < 0)
check("...and its magnitude is right", abs(abs(sydney) - 33.867778) < 1e-5, f"got {sydney}")
check("a mixed-sign tuple does not partially cancel", dms_to_degrees((-33, -52, -4)) < -33.0)

check("millionths of an arcsecond survive",
      abs(dms_to_degrees((0, 0, 0, 500000)) - (0.5 / 3600.0)) < 1e-12)
check("a plain number is accepted too", dms_to_degrees(12.5) == 12.5)
check("None is None, not 0", dms_to_degrees(None) is None,
      "0.0 would be a real place off the coast of Africa")

# --- round-trip: a writer and a reader that disagree is the defect this repo has a memory about ----
for v in (51.507222, -33.867778, 0.0, 179.999999, -0.000278, 45.5):
    back = dms_to_degrees(degrees_to_dms(v))
    check(f"{v} round-trips through the IFC compound form", abs(back - v) < 1e-6,
          f"got {back}")

check("a negative angle carries its sign on every component",
      all(p <= 0 for p in degrees_to_dms(-33.867778)),
      f"got {degrees_to_dms(-33.867778)} — a tuple with mixed signs is not readable back")

# the carry cases: 59.9999999" must not be written as 60"
d, m, s, u = degrees_to_dms(45.0 - 1e-9)
check("a value just under a whole degree does not write 60 seconds", s < 60 and m < 60,
      f"got {(d, m, s, u)}")

# --- true north is measured from +Y, clockwise ----------------------------------------------------
# IFC gives a direction vector, not an angle. Project north is +Y and surveying measures clockwise,
# so it is atan2(x, y) — the reverse of the usual argument order. Swapping them is a mirror error:
# plausible-looking, and it puts east where west should be.
def north_from(x, y):
    return math.degrees(math.atan2(x, y)) % 360.0


check("a vector along +Y is 0 degrees (project north == true north)", north_from(0, 1) == 0.0)
check("a vector along +X is 90 degrees (true north is to the east)", north_from(1, 0) == 90.0)
check("a vector along -X is 270, not 90", north_from(-1, 0) == 270.0,
      "atan2(y, x) would return 180 here — a mirror error that reads as plausible")
check("45 degrees east of project north", abs(north_from(1, 1) - 45.0) < 1e-9)

# --- units match the kernel's LinearUnit -----------------------------------------------------------
check("the unit table matches the kernel's vocabulary",
      set(METRES_PER_UNIT) == {"m", "mm", "cm", "ft", "us-ft"},
      "a parallel vocabulary is the drift this codebase writes tests to prevent")
check("a US survey foot is NOT an international foot",
      METRES_PER_UNIT["us-ft"] != METRES_PER_UNIT["ft"],
      "2 ppm — about 0.6 m across a state-plane zone, which is a real setting-out error")
check("millimetres are millimetres", METRES_PER_UNIT["mm"] == 0.001)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_geo_ref OK")
