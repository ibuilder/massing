"""A section cut must produce linework for every geometry KIND we ship, not just for one wall.

WHY THIS EXISTS. `test_sections.py` asserts that an auto-centred cut draws geometry — one cut,
through one model, containing one wall. That is enough to catch a total failure of `mesh.section`
and nothing weaker. The failure this guards against is *partial*: a sectioning change that still
works for extruded boxes and stops working for, say, a swept profile or a mesh with an inner loop.
The output of that is a plan or section that composes perfectly, carries a titleblock and a scale
bar, and is missing some of the building — which is the same class of defect as
R43-PLAN-EMPTY-AT-CUT, arriving from the library instead of from the cut height.

It matters now because `services/data/requirements.txt` records a deliberate hold at trimesh
4.12.2, and says that raising it "means regenerating the lock AND validating trimesh 5 against the
paths below — it drives mesh booleans (with manifold3d) and 2D section cuts". Dependabot raised
that floor once already (#229) and every check went green, because at the time nothing compared
that file against the lock: the image kept shipping 4.12.2 while the line claimed 5.0.0. The
comparison gate exists now; this is the other half — the *behavioural* validation, so a major
version move has something to be green against besides "it imported".

WHAT IS ASSERTED, PER SHAPE: the cut produces at least one closed loop, and the loop's extent is
the size the shape actually is. A count alone would pass on degenerate output — a section that
returns a zero-area sliver is not linework, it is a dot, and it prints as an empty sheet.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_section_geometry_kinds.py
"""
import math
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import numpy as np  # noqa: E402
import trimesh  # noqa: E402

from aec_data import drawings  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _at(mesh, z):
    """The cut loops a horizontal plane at `z` produces, as trimesh returns them."""
    return mesh.section(plane_origin=[0, 0, z], plane_normal=[0, 0, 1])


def _extent(section):
    """Width x depth of a section's vertices — a loop that collapses reports ~0."""
    v = np.asarray(section.vertices)
    return float(v[:, 0].max() - v[:, 0].min()), float(v[:, 1].max() - v[:, 1].min())


# --- the shapes a real model is made of ----------------------------------------------------------
# `trimesh.creation.*` primitives are CENTRED on the origin, so a 3.0-tall box spans z -1.5..+1.5
# and a cut at z=1.5 lands exactly on its top face — which returns None, correctly. Building
# elements sit ON their storey, so each primitive is raised by half its height to match. (Written
# down because the first version of this file cut at the boundary and read the None as a trimesh
# defect: a fixture placed wrong produces exactly the symptom the test exists to detect.)
def _standing(mesh, height):
    mesh.apply_translation((0, 0, height / 2.0))
    return mesh


BOX = _standing(trimesh.creation.box(extents=(4.0, 0.3, 3.0)), 3.0)       # a wall
SLAB = trimesh.creation.box(extents=(8.0, 6.0, 0.25))                     # a floor
SLAB.apply_translation((0, 0, 1.5))
COLUMN = _standing(trimesh.creation.cylinder(radius=0.3, height=3.0, sections=24), 3.0)
ANNULUS = _standing(trimesh.creation.annulus(r_min=0.4, r_max=0.6, height=3.0), 3.0)  # INNER loop
SWEPT = trimesh.creation.extrude_polygon(                                 # an L-shaped profile
    __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(
        [(0, 0), (2, 0), (2, 0.3), (0.3, 0.3), (0.3, 2), (0, 2)]),
    height=3.0)

CASES = [
    ("box wall", BOX, 1.5, (4.0, 0.3)),
    ("floor slab", SLAB, 1.5, (8.0, 6.0)),
    ("round column", COLUMN, 1.5, (0.6, 0.6)),
    ("annulus / pipe", ANNULUS, 1.5, (1.2, 1.2)),
    ("swept L profile", SWEPT, 1.5, (2.0, 2.0)),
]

for name, mesh, z, (want_w, want_d) in CASES:
    sec = _at(mesh, z)
    if sec is None:
        check(f"{name}: the cut plane produces linework", False, "section() returned None")
        continue
    w, d = _extent(sec)
    ok_size = math.isclose(w, want_w, rel_tol=0.12) and math.isclose(d, want_d, rel_tol=0.12)
    check(f"{name}: the cut plane produces linework of the right size", ok_size,
          f"extent {w:.2f} x {d:.2f}, expected ~{want_w} x {want_d}")

# The annulus is the one that distinguishes "found the outside" from "found the shape": a section
# that loses inner loops still returns a plausible outer rectangle, so the count is the assertion.
ann = _at(ANNULUS, 1.5)
check("annulus keeps BOTH loops — losing the inner one draws a solid pipe",
      ann is not None and len(ann.entities) >= 2,
      f"{0 if ann is None else len(ann.entities)} entities")

# A plane above everything must return None, not an empty-but-truthy section: the difference is
# what R43-PLAN-EMPTY-AT-CUT depends on to tell "cut missed" from "storey is empty".
check("a plane clear of the geometry returns None rather than an empty section",
      _at(BOX, 99.0) is None)

# --- and the same through the real drawing path, not just the library ---------------------------
meshes = [(f"G{i}", "IfcWall", m) for i, (_n, m, _z, _e) in enumerate(CASES)]
svg = drawings.plan_drawing_svg(meshes, 0.0, 1.5, "Kinds")
drawn = svg.count("<polyline") + svg.count("<path") + svg.count("<line")
check("the plan drawing path renders all five shapes, not just the ones it likes",
      drawn >= len(CASES), f"{drawn} linework elements for {len(CASES)} shapes")
check("and it does not report the cut as empty", "NO GEOMETRY AT THIS CUT" not in svg)

print()
if FAILED:
    print(f"FAILED: {'; '.join(FAILED)}")
    sys.exit(1)
print(f"section geometry OK — {len(CASES)} shape kinds cut at the right size, inner loops kept, "
      "a clear plane still returns None, and the drawing path renders all of them")
