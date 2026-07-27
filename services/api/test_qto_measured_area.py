"""
The area an estimate prices must be the area a quantity surveyor would measure — not the surface
area of the mesh.

Found by authoring a 12x8 m house through the live API and hand-checking the estimate: the roof came
back as 202 m² (it is a 96 m² roof) and the four walls as 236.32 m² (the paintable face is 108 m²).
Both matched "sum of every triangle in the solid" to the cent. Nothing failed; the money was just
about double. These tests pin the arithmetic so it cannot drift back.
"""
import math
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data import qto  # noqa: E402

FAILED = []


def check(label, got, want, tol=0.01):
    ok = got is not None and math.isclose(got, want, rel_tol=tol)
    print(f"{'PASS' if ok else 'FAIL'}  {label}: got {got}, want {want}")
    if not ok:
        FAILED.append(label)


class FakeGeo:
    """A box mesh: 8 corners is all `_bbox_dims` reads, and we state the surface separately."""

    def __init__(self, dx, dy, dz):
        self.dims = (dx, dy, dz)
        self.verts = [
            0.0, 0.0, 0.0,  dx, 0.0, 0.0,  dx, dy, 0.0,  0.0, dy, 0.0,
            0.0, 0.0, dz,   dx, 0.0, dz,   dx, dy, dz,   0.0, dy, dz,
        ]


class FakeEl:
    def __init__(self, cls):
        self.cls = cls

    def is_a(self, other=None):
        return self.cls if other is None else other == self.cls


def surface_of(dx, dy, dz):
    return 2 * (dx * dy + dy * dz + dx * dz)


# --- the two numbers from the live house -----------------------------------------------------
# Roof: 12 x 8 plan, 0.25 thick. A roofer prices 96 m².
roof_geo, roof = FakeGeo(12.0, 8.0, 0.25), FakeEl("IfcRoof")
qto._shape = type("S", (), {"get_area": staticmethod(lambda g: surface_of(*g.dims))})
check("roof is measured in PLAN", qto._measured_area(roof, roof_geo), 96.0)
check("  (the surface area it used to return)", surface_of(12.0, 8.0, 0.25), 202.0)

# One 12 m wall, 2.7 high, 0.2 thick. A painter prices 32.4 m² a face.
wall_geo, wall = FakeGeo(12.0, 0.2, 2.7), FakeEl("IfcWall")
check("wall is measured on ELEVATION", qto._measured_area(wall, wall_geo), 32.4)
check("  4 walls of the house together", 2 * (12.0 * 2.7) + 2 * (8.0 * 2.7), 108.0)

# A slab is plan-measured like a roof.
check("slab is measured in PLAN",
      qto._measured_area(FakeEl("IfcSlab"), FakeGeo(12.0, 8.0, 0.15)), 96.0)

# --- what must NOT change --------------------------------------------------------------------
# A duct's area genuinely IS its skin — there is no plan or face measure that means anything.
duct_geo = FakeGeo(0.3, 0.3, 4.0)
check("a duct keeps its full surface area",
      qto._measured_area(FakeEl("IfcDuctSegment"), duct_geo), surface_of(0.3, 0.3, 4.0))

# An unreadable mesh must not produce zero — a takeoff with a silent 0 prices the element out of
# existence, which is worse than a slightly wrong number.
class NoVerts:
    verts = []
    dims = (1.0, 1.0, 1.0)


check("unreadable mesh falls back, never to 0",
      qto._measured_area(FakeEl("IfcRoof"), NoVerts()), surface_of(1.0, 1.0, 1.0))

# --- the property that makes this a bug, stated directly ---------------------------------------
over = surface_of(12.0, 8.0, 0.25) / 96.0
print(f"\nthe roof was over-measured by {over:.2f}x before this fix")
if over < 2.0:
    FAILED.append("the over-measurement this test exists for is not reproduced")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_qto_measured_area OK")
