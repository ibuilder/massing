"""DXF quantity takeoff — build a synthetic DXF and check per-layer lengths / areas / block counts.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_dxf_takeoff.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_dxf.db"
os.environ["STORAGE_DIR"] = "./test_storage_dxf"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_dxf.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ezdxf  # noqa: E402

from aec_api import dxf_takeoff  # noqa: E402

# --- build a small drawing in metres: a 10x5 closed room on WALLS, a 12m pipe run on PLUMB,
#     two door blocks on DOORS ---
doc = ezdxf.new()
doc.header["$INSUNITS"] = 6  # metres
msp = doc.modelspace()
msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={"layer": "WALLS"})  # perim 30, area 50
msp.add_line((0, 0), (12, 0), dxfattribs={"layer": "PLUMB"})           # 12 m
blk = doc.blocks.new(name="DOOR")
blk.add_line((0, 0), (0.9, 0))
msp.add_blockref("DOOR", (1, 1), dxfattribs={"layer": "DOORS"})
msp.add_blockref("DOOR", (3, 1), dxfattribs={"layer": "DOORS"})

fd, tmp = tempfile.mkstemp(suffix=".dxf")
os.close(fd)
doc.saveas(tmp)

t = dxf_takeoff.takeoff(tmp)
os.remove(tmp)

assert t["units"] == "m" and not t["unitless"], t
by = {ly["layer"]: ly for ly in t["layers"]}
# WALLS: closed poly → perimeter 30 m, area 50 m²
assert abs(by["WALLS"]["length_m"] - 30.0) < 1e-6, by["WALLS"]
assert abs(by["WALLS"]["area_m2"] - 50.0) < 1e-6, by["WALLS"]
# PLUMB: a 12 m line, no area
assert abs(by["PLUMB"]["length_m"] - 12.0) < 1e-6 and by["PLUMB"]["area_m2"] == 0.0, by["PLUMB"]
# DOORS: two block inserts, no length/area
assert by["DOORS"]["inserts"] == 2, by["DOORS"]
assert t["total_length_m"] == round(30.0 + 12.0, 3), t["total_length_m"]
assert any(b["block"] == "DOOR" and b["count"] == 2 for b in t["blocks"]), t["blocks"]
print(f"dxf takeoff: {t['layer_count']} layers, {t['total_length_m']} m linear, "
      f"{t['total_area_m2']} m2, blocks {t['blocks']}")

# --- unit conversion: same geometry declared in millimetres converts to metres ---
doc2 = ezdxf.new()
doc2.header["$INSUNITS"] = 4  # mm
doc2.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "X"})   # 1000 mm = 1 m
fd, tmp2 = tempfile.mkstemp(suffix=".dxf")
os.close(fd)
doc2.saveas(tmp2)
t2 = dxf_takeoff.takeoff(tmp2)
os.remove(tmp2)
assert t2["units"] == "mm" and abs(t2["total_length_m"] - 1.0) < 1e-6, t2

# --- a non-DXF file raises a clean RuntimeError (→ 400 at the endpoint) ---
fd, bad = tempfile.mkstemp(suffix=".dxf")
with os.fdopen(fd, "w") as fh:
    fh.write("this is not a dxf")
try:
    dxf_takeoff.takeoff(bad)
    raise AssertionError("expected RuntimeError on a non-DXF file")
except RuntimeError:
    pass
finally:
    os.remove(bad)

# --- endpoint: upload the DXF, get quantities back ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

c = TestClient(app)
doc3 = ezdxf.new(); doc3.header["$INSUNITS"] = 6
doc3.modelspace().add_line((0, 0), (5, 0), dxfattribs={"layer": "A"})
fd, tmp3 = tempfile.mkstemp(suffix=".dxf")
os.close(fd)
doc3.saveas(tmp3)
with open(tmp3, "rb") as fh:
    r = c.post("/projects/p1/takeoff/dxf", files={"file": ("plan.dxf", fh, "application/dxf")})
os.remove(tmp3)
assert r.status_code == 200 and abs(r.json()["total_length_m"] - 5.0) < 1e-6, (r.status_code, r.text[:200])
# a junk upload → 400, not 500
r2 = c.post("/projects/p1/takeoff/dxf", files={"file": ("x.dxf", b"nope", "application/dxf")})
assert r2.status_code == 400, r2.status_code

print("test_dxf_takeoff OK")
