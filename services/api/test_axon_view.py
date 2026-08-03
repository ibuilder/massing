"""CANVAS-PEER — a 3D view is a DRAWING, not a screenshot of one.

The asymmetry this closes: a plan went model → `plan_svg` → sheet → PDF as vector linework derived
from the geometry, while "3D" went canvas → `toDataURL` → a raster hero image. Offering the two as
interchangeable canvas modes while only one could be placed on a sheet would have been a UI promise
the data could not keep — so the sheet layer gains an `axon` viewport that composes like any other.

What is asserted here is the difference between a drawing and a picture:

  1. the projection is a real orthonormal basis (a wrong basis silently skews every drawing, and a
     skewed axonometric still *looks* plausible — which is exactly why it needs a test);
  2. an arbitrary view direction works, because `elevation_outlines` reads `_DIRS` and is
     structurally unable to look down a diagonal;
  3. **the GlobalId survives the projection**, per the non-negotiable that elements are referenced by
     GUID — this is what makes an axonometric clickable and the mode switch worth building;
  4. depth sorts far → near, so a painter's draw hides what is behind;
  5. it composes onto a sheet through the same path as a plan.

`bake` is not used here: these tests build trimesh boxes directly, so they exercise the projection
rather than the IFC loader, and they stay fast enough to run every time.
"""
from __future__ import annotations

import sys

import numpy as np
import trimesh

sys.path.insert(0, "../data/src")
from aec_data.drawings import axon_basis, axon_outlines  # noqa: E402
from aec_data.sheet_layout import compose_viewports  # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        FAILS.append(f"{name}{(' — ' + detail) if detail else ''}")
        print(f"  FAIL {name}  {detail}")


def _box(guid: str, cls: str, x: float, y: float, z: float, s: float = 1.0):
    m = trimesh.creation.box(extents=(s, s, s))
    m.apply_translation((x, y, z))
    return (guid, cls, m)


# --- 1. the basis is a real rotation -------------------------------------------------------------
print("axon_basis")
B = axon_basis()
check("rows are unit length", all(abs(np.linalg.norm(r) - 1.0) < 1e-9 for r in B),
      f"norms={[round(float(np.linalg.norm(r)), 6) for r in B]}")
check("rows are mutually orthogonal",
      max(abs(float(B[i] @ B[j])) for i, j in ((0, 1), (0, 2), (1, 2))) < 1e-9)
check("it is a rotation, not a reflection (det=+1)", abs(float(np.linalg.det(B)) - 1.0) < 1e-9,
      f"det={float(np.linalg.det(B)):.6f}")

# The default must be a TRUE isometric: the three world axes foreshorten equally. That is the claim
# "isometric" makes, and a rounded 30/45 that merely looks right would fail this.
lens = [float(np.linalg.norm((B @ np.eye(3)[k])[:2])) for k in range(3)]
check("default is a true isometric — all three axes foreshorten equally",
      max(lens) - min(lens) < 1e-6, f"projected axis lengths={[round(v, 6) for v in lens]}")

# --- 2. an arbitrary direction works ------------------------------------------------------------
print("arbitrary view directions")
for az, el in ((0.0, 0.0), (45.0, 35.264), (137.0, 12.5), (300.0, 80.0)):
    Bx = axon_basis(az, el)
    ok = (abs(float(np.linalg.det(Bx)) - 1.0) < 1e-9
          and max(abs(float(Bx[i] @ Bx[j])) for i, j in ((0, 1), (0, 2), (1, 2))) < 1e-9)
    check(f"basis valid at az={az} el={el}", ok)

# straight down is the degenerate case the basis has to special-case, or `right` is undefined
check("looking straight down does not produce a NaN basis",
      not np.isnan(axon_basis(0.0, 90.0)).any())

# --- 3. GUID survives, and depth sorts far -> near ------------------------------------------------
print("axon_outlines")
meshes = [_box("GUID-NEAR", "IfcWall", 4.0, 4.0, 0.0),
          _box("GUID-FAR", "IfcWall", -4.0, -4.0, 0.0),
          _box("GUID-MID", "IfcColumn", 0.0, 0.0, 0.0)]
out = axon_outlines(meshes)
check("every element produced a silhouette", len(out) == 3, f"got {len(out)}")
check("the GlobalId survives the projection",
      {r[0] for r in out} == {"GUID-NEAR", "GUID-FAR", "GUID-MID"}, f"got {[r[0] for r in out]}")
check("the IFC class survives too", {r[1] for r in out} == {"IfcWall", "IfcColumn"})
check("hulls are closed 2-D rings", all(r[2].ndim == 2 and r[2].shape[1] == 2 for r in out))
check("sorted far -> near for a painter's draw",
      [r[3] for r in out] == sorted(r[3] for r in out), f"depths={[round(r[3], 3) for r in out]}")
# at az=45 the +x+y corner faces the viewer, so NEAR must come last
check("the element nearest the viewer draws last", out[-1][0] == "GUID-NEAR",
      f"order={[r[0] for r in out]}")

# --- 4. it is a PROJECTION, not a copy of the plan ------------------------------------------------
# A stack of boxes differing only in Z is one blob in plan; under an axonometric they separate. This
# is the assertion that would fail if `axon` silently fell through to the plan path.
print("axon differs from plan")
stack = [_box("A", "IfcSlab", 0.0, 0.0, 0.0), _box("B", "IfcSlab", 0.0, 0.0, 5.0)]
sep = axon_outlines(stack)
cy = [float(r[2][:, 1].mean()) for r in sep]
check("elements stacked in Z separate vertically on the page", abs(cy[0] - cy[1]) > 1.0,
      f"page-Y centroids={[round(v, 3) for v in cy]}")

# a 90° azimuth change must actually change the drawing
rot = axon_outlines(meshes, azimuth_deg=135.0)
same = all(np.allclose(a[2], b[2]) for a, b in zip(sorted(out, key=lambda r: r[0]),
                                                   sorted(rot, key=lambda r: r[0]), strict=True))
check("rotating the view changes the geometry drawn", not same)

# --- 5. it composes onto a sheet like any other viewport -------------------------------------------
print("sheet composition")
# NOTE ON THE KEYS: this reads `views`, `label` and `sub` because that is what `compose_viewports`
# actually returns. The first version asserted `viewports` / `title` / `note` — a shape invented
# rather than read — and reported "the sheet accepted 0 viewports", which looked exactly like the
# feature being broken. **Assert against the reader you did not write.**
layout = compose_viewports(meshes, [{"kind": "axon", "title": "ISO VIEW"}], page="A3")
vws = layout.get("views") or []
check("the sheet accepted an axon viewport", len(vws) == 1, f"got {len(vws)}")
if vws:
    v = vws[0]
    check("it carries placed polylines to draw", len(v.get("polys") or []) > 0)
    check("it is titled", (v.get("label") or "") == "ISO VIEW", f"label={v.get('label')!r}")
    check("it says NTS — an axonometric has no drawing scale",
          "NTS" in (v.get("sub") or ""), f"sub={v.get('sub')!r}")
    check("its kind survives into the sheet", v.get("kind") == "axon", f"kind={v.get('kind')!r}")
    # An axonometric has no true paper scale, so it must not claim a denominator.
    check("no scale denominator is asserted", v.get("scale_denom") is None,
          f"scale_denom={v.get('scale_denom')!r}")

# a plan and an axon of the same model, side by side — the peer claim, end to end
# `cut_height: 0.0` is deliberate. The default 1.2 m is the right cut for a real storey, and it sails
# clean over these 1 m test cubes — producing an empty plan that looks exactly like a broken plan.
# The fixture has to intersect the geometry for the comparison to mean anything.
both = compose_viewports(meshes, [{"kind": "plan", "elevation": 0.0, "cut_height": 0.0,
                                   "rect": [0, 0, 0.5, 1]},
                                  {"kind": "axon", "rect": [0.5, 0, 0.5, 1]}], page="A3")
bv = both.get("views") or []
check("a plan and an axonometric compose on ONE sheet", len(bv) == 2, f"got {len(bv)}")
check("both viewports drew geometry", all(len(v.get("polys") or []) > 0 for v in bv),
      f"poly counts={[len(v.get('polys') or []) for v in bv]}")

print()
if FAILS:
    print(f"FAILED: {len(FAILS)} check(s)")
    for f in FAILS:
        print(f"  - {f}")
    raise SystemExit(1)
print("test_axon_view OK")
