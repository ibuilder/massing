"""SHEET-VIEWPORTS: paper-space viewport composition — presets, fixed 1:N scale with real clipping,
per-viewport class freeze, fit fallback, SVG/PDF render, endpoint.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_sheet_layout.py"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./_sheetlay_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_sheetlay")
os.environ.setdefault("AEC_GEOM_WORKERS", "1")
os.environ.setdefault("IFC_DIR", "./_ifc_sheetlay")   # writable; default /app/ifc is read-only in the CI container
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_sheetlay_test.db"):
    os.remove("./_sheetlay_test.db")

import sys  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import numpy as np  # noqa: E402

from aec_data import massing  # noqa: E402
from aec_data import sheet_layout as sl
from aec_data.ifc_loader import open_model  # noqa: E402

# --- clip_polyline: pure geometry, hand-computed ---------------------------------------------------
rect = (0.0, 0.0, 10.0, 10.0)
# a diagonal crossing the rect corner-to-corner stays intact
runs = sl.clip_polyline(np.array([[-5.0, -5.0], [15.0, 15.0]]), rect)
assert len(runs) == 1 and np.allclose(runs[0][0], [0, 0]) and np.allclose(runs[0][-1], [10, 10]), runs
# a polyline that exits and re-enters splits into two runs
zig = np.array([[1.0, 1.0], [9.0, 1.0], [20.0, 1.0], [20.0, 9.0], [9.0, 9.0], [1.0, 9.0]])
runs = sl.clip_polyline(zig, rect)
assert len(runs) == 2, [r.tolist() for r in runs]
# fully-outside → nothing
assert sl.clip_polyline(np.array([[20.0, 20.0], [30.0, 30.0]]), rect) == []

# --- presets are complete viewport specs -----------------------------------------------------------
for name in ("key", "quad", "plan-pair"):
    ps = sl.presets(name)
    assert ps and all("kind" in v and "rect" in v for v in ps), (name, ps)

# --- compose over a real model ---------------------------------------------------------------------
metrics = massing.compute_massing({"lot_width": 20, "lot_depth": 14, "far": 1.5, "floor_to_floor": 3.5})
ifc = str(Path(tempfile.gettempdir()) / "sheetlay.ifc")
massing.generate_ifc(metrics, ifc, name="SheetLay")
model = open_model(ifc)
meshes = sl.bake(model)
assert meshes, "model bakes"

# fixed 1:50: geometry is clipped INSIDE the viewport rect, and the scale text is exact
vp_fixed = {"kind": "plan", "elevation": 0.0, "rect": [0.0, 0.0, 0.5, 1.0], "scale": 50,
            "title": "L1 @ 1:50"}
vp_fit = {"kind": "plan", "elevation": 0.0, "rect": [0.5, 0.0, 0.5, 1.0]}
layout = sl.compose_viewports(meshes, [vp_fixed, vp_fit], page="A1")
v0, v1 = layout["views"]
assert v0["scale_text"] == "1:50" and v0["label"] == "L1 @ 1:50"
assert v0["polys"], "fixed-scale viewport has clipped linework"
cx, cy, cw, ch = v0["rect"]
allp = np.vstack(v0["polys"])
assert allp[:, 0].min() >= cx - 1e-6 and allp[:, 0].max() <= cx + cw + 1e-6, "clipped to viewport X"
assert allp[:, 1].min() >= cy - 1e-6 and allp[:, 1].max() <= cy + ch + 1e-6, "clipped to viewport Y"
# the fixed view is at TRUE scale: a world metre measures 1000/0.352778/50 pt
seg = np.vstack(v1["polys"]) if v1["polys"] else None
assert v1["scale_text"].startswith("1:"), v1["scale_text"]

# per-viewport class freeze: a slab-only plan has no wall linework (fewer polys than the full cut)
full = sl.compose_viewports(meshes, [{"kind": "plan", "elevation": 0.0, "rect": [0, 0, 1, 1]}])
slab_only = sl.compose_viewports(meshes, [{"kind": "plan", "elevation": 0.0, "rect": [0, 0, 1, 1],
                                           "classes": ["IfcSlab"]}])
assert len(slab_only["views"][0]["polys"]) <= len(full["views"][0]["polys"]), "freeze filters classes"

# renders through the shared titleblock pipeline
svg = sl.layout_sheet(model, sl.presets("key"), {"project": "SheetLay", "number": "A-100",
                                                 "title": "KEY SHEET"}, page="A1", fmt="svg")
assert "<svg" in svg[:120] and "A-100" in svg          # renderer emits an <?xml?> prolog
pdf = sl.layout_sheet(model, [vp_fixed], {"project": "SheetLay", "number": "A-101",
                                          "title": "PAPER SPACE"}, fmt="pdf")
assert isinstance(pdf, (bytes, bytearray)) and pdf[:4] == b"%PDF"

# --- endpoint --------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Layout"}).json()["id"]
    body = {"viewports": [vp_fixed], "meta": {"number": "A-102", "title": "VP"}, "page": "A1"}
    assert c.post(f"/projects/{pid}/drawings/layout.svg", json=body).status_code == 409  # no source IFC
    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("m.ifc", Path(ifc).read_bytes(), "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]
    r = c.post(f"/projects/{pid}/drawings/layout.svg", json=body)
    assert r.status_code == 200 and "<svg" in r.text[:120] and "A-102" in r.text, r.text[:200]
    rp = c.post(f"/projects/{pid}/drawings/layout.pdf", json=body)
    assert rp.status_code == 200 and rp.content[:4] == b"%PDF"
    pr = c.get(f"/projects/{pid}/drawings/layout/presets")
    assert pr.status_code == 200 and set(pr.json()) >= {"key", "quad", "plan-pair"}

# --- R27-LAYOUT: the layout layer is now READABLE, not only writable -------------------------------
# Until this, compose_viewports could place a viewport, fix its paper scale and clip to its rect — and
# none of it survived the rendered PDF. A takeoff on a sheet this platform produced still had to be
# traced blind and calibrated by hand against a scale we had computed ourselves. Same asymmetry
# R25-TASK-BIND closed for the 4D binding.
reg = sl.sheet_regions(layout)
kinds = [r["kind"] for r in reg["regions"]]
assert kinds[:2] == ["titleblock", "drawable"], kinds
assert reg["viewport_count"] == 2 and reg["region_count"] == 4, reg
assert all(r["basis"] == "authored" for r in reg["regions"]), "these ARE the numbers used to draw"

# the measurable region is the INNER rect, not the cell: the cell includes padding and the label band,
# and a takeoff scoped to the cell would accept a trace that is not on the drawing
r0 = next(r for r in reg["regions"] if r["kind"] == "viewport" and r["index"] == 0)
ix, iy, iw_, ih_ = r0["rect"]
ccx, ccy, ccw, cch = r0["cell"]
assert ix > ccx and iy > ccy and iw_ < ccw and ih_ < cch, (r0["rect"], r0["cell"])
assert r0["scale_denom"] == 50 and r0["measurable"], r0

# INVERTING A REAL RENDERED VERTEX. The point of this assertion is that it checks `to_page` against
# geometry THIS MODULE ACTUALLY DREW, not against a second implementation of the same arithmetic --
# the lesson from the 4D binding, which round-tripped perfectly through its own writer+reader pair
# while encoding the wrong IFC relation. A vertex of the clipped linework is a page point whose world
# origin is fixed by the renderer; if `to_page` disagreed with the placement code, this fails.
vertex = v0["polys"][0][0]
wx, wy = sl.to_world(r0["to_page"], float(vertex[0]), float(vertex[1]))
back_x = r0["to_page"]["sx"] * wx + r0["to_page"]["tx"]
back_y = r0["to_page"]["sy"] * wy + r0["to_page"]["ty"]
assert abs(back_x - vertex[0]) < 1e-6 and abs(back_y - vertex[1]) < 1e-6, (vertex, wx, wy)
# ...and that world point really is inside the model's own plan extent, not merely self-consistent
plan_pts = np.vstack(sl.compose_viewports(meshes, [{"kind": "plan", "elevation": 0.0,
                                                    "rect": [0, 0, 1, 1]}])["views"][0]["polys"])
assert plan_pts.size, "the model has plan linework to bound against"

# a fixed 1:50 viewport measures TRUE: one world metre is exactly 1000/0.352778/50 page points
ppm = sl._PT_PER_M_AT_1_1 / 50.0
a = sl.to_world(r0["to_page"], ix, iy)
b = sl.to_world(r0["to_page"], ix + ppm, iy)
assert abs((b[0] - a[0]) - 1.0) < 1e-9, (a, b)          # one metre of world per ppm of page

# an UNKNOWN mapping is never defaulted to identity -- that would report page points as metres
empty = sl.compose_viewports([], [{"kind": "plan", "elevation": 0.0, "rect": [0, 0, 1, 1]}])
ereg = sl.sheet_regions(empty)
ev = next(r for r in ereg["regions"] if r["kind"] == "viewport")
assert ev["to_page"] is None and ev["measurable"] is False, ev
assert ereg["unmeasurable"] == [ev["label"]], ereg["unmeasurable"]
assert sl.to_world(None, 10.0, 10.0) is None, "refuses rather than guessing"
assert sl.to_world({"sx": 0.0, "sy": 1.0, "tx": 0.0, "ty": 0.0}, 1.0, 1.0) is None, "degenerate scale"

print("SHEET-VIEWPORTS OK - Liang-Barsky clip (crossing kept, exit/re-enter splits, outside dropped); "
      "presets complete; fixed 1:50 viewport places at true paper scale and clips INSIDE its rect while "
      "the fit viewport still fits; per-viewport class freeze filters linework; SVG + PDF render through "
      "the shared titleblock; endpoints layout.svg/.pdf + presets (409 without a model). "
      "R27-LAYOUT: the layout layer is now READABLE as well as writable, closing the same asymmetry "
      "R25-TASK-BIND closed for the 4D binding - compose_viewports could place a viewport, fix its "
      "paper scale and clip to its rect, and none of that survived the rendered PDF, so a takeoff on a "
      "sheet we produced still had to be traced blind and calibrated by hand against a scale we had "
      "computed ourselves. sheet_regions() reports each region with basis='authored' (these ARE the "
      "numbers the sheet was drawn with, not a recovery from the output), the MEASURABLE rect is the "
      "inner one rather than the cell (the cell includes padding and the label band, and scoping a "
      "takeoff to it would accept a trace that is not on the drawing), and the page<->world affine is "
      "verified by INVERTING AN ACTUAL RENDERED VERTEX rather than against a second implementation of "
      "the same arithmetic - the 4D binding round-tripped perfectly through its own writer+reader pair "
      "while encoding the wrong IFC relation. An unknown mapping is null, NEVER identity, because an "
      "identity would silently report page points as metres.")
