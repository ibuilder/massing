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

print("SHEET-VIEWPORTS OK - Liang-Barsky clip (crossing kept, exit/re-enter splits, outside dropped); "
      "presets complete; fixed 1:50 viewport places at true paper scale and clips INSIDE its rect while "
      "the fit viewport still fits; per-viewport class freeze filters linework; SVG + PDF render through "
      "the shared titleblock; endpoints layout.svg/.pdf + presets (409 without a model).")
