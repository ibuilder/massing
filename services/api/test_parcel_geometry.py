"""PARCEL-IMPORT — cadastral parcel geometry (GeoJSON/WKT) → area/perimeter/centroid + FAR/coverage/height
compliance vs a zoning envelope.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_parcel_geometry.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_parcel_geometry.db"
os.environ["STORAGE_DIR"] = "./test_storage_parcelgeo"
os.environ.pop("AEC_RBAC", None)

from aec_api import parcel_geometry as pg  # noqa: E402

# --- a 100×50 m rectangle in projected metres: exact shoelace area -------------------------------
rect = {"type": "Polygon", "coordinates": [[[1000, 2000], [1100, 2000], [1100, 2050], [1000, 2050], [1000, 2000]]]}
r = pg.analyze(geojson=rect, parcel_id="LOT-42")
assert r["area_m2"] == 5000.0 and r["perimeter_m"] == 300.0, r
assert r["area_acres"] == 1.236 and r["vertices"] == 4 and r["coordinates_were_lonlat"] is False, r
assert r["parcel_id"] == "LOT-42" and r["bbox"]["maxx"] == 1100, r

# --- same via WKT + a Feature wrapper --------------------------------------------------------------
w = pg.analyze(wkt="POLYGON ((1000 2000, 1100 2000, 1100 2050, 1000 2050, 1000 2000))")
assert w["area_m2"] == 5000.0, w
f = pg.analyze(geojson={"type": "Feature", "geometry": rect, "properties": {}})
assert f["area_m2"] == 5000.0, f

# --- a lon/lat ring converts equirectangularly (~111.19 m per 0.001° lat at the equator) -----------
ll = {"type": "Polygon", "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]]}
g = pg.analyze(geojson=ll)
assert g["coordinates_were_lonlat"] is True, g
assert abs(g["area_m2"] - 111.19**2) / 111.19**2 < 0.01, g["area_m2"]        # ~12,363 m² within 1%

# --- zoning compliance: FAR over, coverage under, height at limit ---------------------------------
z = pg.analyze(geojson=rect, zoning={"max_far": 2.0, "max_coverage": 0.6, "max_height_m": 30},
               proposal={"gfa_m2": 12_000, "footprint_m2": 2_000, "height_m": 30})
comp = z["compliance"]
by = {c["metric"]: c for c in comp["checks"]}
assert by["FAR"]["value"] == 2.4 and by["FAR"]["ok"] is False and by["FAR"]["max_gfa_m2"] == 10_000.0, by["FAR"]
assert by["coverage"]["value"] == 0.4 and by["coverage"]["ok"] is True and by["coverage"]["slack"] == 0.2, by["coverage"]
assert by["height_m"]["ok"] is True, by["height_m"]                           # at the limit = compliant
assert comp["ok"] is False and comp["violations"] == ["FAR"], comp

# no zoning limits given → checks report values with ok=None, overall None
n = pg.analyze(geojson=rect, proposal={"gfa_m2": 12_000})
assert n["compliance"]["checks"][0]["ok"] is None and n["compliance"]["ok"] is None, n["compliance"]

# --- ReDoS hardening (CodeQL py/polynomial-redos): crafted whitespace must return fast -------------
import time as _time

for evil in ("POLYGON ((" + " " * 90_000, "POLYGON" + " " * 19_000 + "((1 2, 3 4, 5 6))"):
    t0 = _time.perf_counter()
    try:
        pg.analyze(wkt=evil)
    except (ValueError, TypeError):
        pass
    assert _time.perf_counter() - t0 < 0.1, "crafted WKT must parse/reject in linear time"
try:
    pg.analyze(wkt="POLYGON ((" + "1 1, " * 10_000 + "1 1))" + "x" * 20_000)   # over the size cap
    raise AssertionError("oversized WKT must raise")
except ValueError as e:
    assert "too large" in str(e)

# --- PARCEL-SHAPE: a repeated vertex must not reach offset_polygon ---------------------------------
# Stripping the CLOSING duplicate is not enough — an interior repeat survives it. `offset_polygon`
# divides by each edge's length and guards with `ln or 1e-9`, so a zero-length edge does not raise:
# the normal becomes ~1e9 and that vertex is left UNMOVED while its neighbours inset. The result is
# a plausible polygon with the wrong area, which is worse than a refusal because nothing looks
# broken. Raised in review, and asserted through the real offset rather than on the ring alone.
import sys as _sys0  # noqa: E402

_sys0.path.insert(0, os.path.join("..", "data", "src"))
from aec_data.massing import offset_polygon as _offset  # noqa: E402

dup = {"type": "Polygon", "coordinates": [[[1000, 2000], [1000, 2000], [1050, 2000], [1050, 2050],
                                           [1000, 2050], [1000, 2000]]]}
d = pg.analyze(geojson=dup)
assert d["ring_m"] == [[0.0, 0.0], [50.0, 0.0], [50.0, 50.0], [0.0, 50.0]], d["ring_m"]
assert d["vertices"] == 4 and d["area_m2"] == 2500.0, d
assert _offset(d["ring_m"], 5) == [[5.0, 5.0], [45.0, 5.0], [45.0, 45.0], [5.0, 45.0]], _offset(d["ring_m"], 5)
# ...and a boundary that is only repeats is refused rather than emitted as a 1-point ring.
for degenerate in ([[0, 0], [0, 0], [0, 0]], [[5, 5], [5, 5]]):
    try:
        pg.analyze(geojson={"type": "Polygon", "coordinates": [degenerate]})
        raise AssertionError(f"expected ValueError for {degenerate!r}")
    except ValueError:
        pass

# --- PARCEL-SHAPE: the projected ring comes BACK, and it sizes a smaller building ------------------
# `analyze` computed the metric ring and threw it away, so the only lot a client could describe was
# `lot_width × lot_depth` — a bounding rectangle, whose area is ALWAYS ≥ the parcel's. The bias runs
# lot area → max GFA → floors → units → the acquisition proforma's IRR, optimistic at every step and
# silent about it.
import sys as _sys  # noqa: E402

_sys.path.insert(0, os.path.join("..", "data", "src"))
from aec_data import massing as _massing  # noqa: E402

# An L-shaped corner lot in projected metres: 1,600 m² inside a 50 × 50 m box.
ell = {"type": "Polygon", "coordinates": [[[1000, 2000], [1050, 2000], [1050, 2020], [1020, 2020],
                                           [1020, 2050], [1000, 2050], [1000, 2000]]]}
e = pg.analyze(geojson=ell)
assert e["area_m2"] == 1600.0 and e["bounding_rect_m2"] == 2500.0, e
assert e["lot_width_m"] == 50.0 and e["lot_depth_m"] == 50.0, e
# Origin-shifted to its own bbox min: real coordinates stay in `bbox`/`centroid` for export, and the
# generated model renders near the scene origin instead of 1 km out.
assert e["ring_m"] == [[0.0, 0.0], [50.0, 0.0], [50.0, 20.0], [20.0, 20.0], [20.0, 50.0], [0.0, 50.0]], e["ring_m"]
assert e["bbox"]["minx"] == 1000, e["bbox"]
# OPEN, no repeated closing vertex — `offset_polygon` divides by each edge's length, and a
# zero-length closing edge hands it a meaningless normal.
assert e["ring_m"][0] != e["ring_m"][-1], e["ring_m"]
assert len(e["ring_m"]) == e["vertices"] == 6, e

# The claim the whole item exists for, measured rather than asserted in prose: the same lot, same
# zoning, sized on the ring vs on the bounding rectangle the two numeric inputs could describe.
sb = {"far": 2.0, "side_setback": 5, "front_setback": 5, "rear_setback": 5}
poly_run = _massing.compute_massing({"lot_polygon": e["ring_m"], **sb})
rect_run = _massing.compute_massing({"lot_width": e["lot_width_m"], "lot_depth": e["lot_depth_m"], **sb})
assert poly_run["lot_area_m2"] == 1600.0 and rect_run["lot_area_m2"] == 2500.0, (poly_run, rect_run)
assert poly_run["buildable_gfa_m2"] == 3200.0, poly_run["buildable_gfa_m2"]
assert rect_run["buildable_gfa_m2"] == 5000.0, rect_run["buildable_gfa_m2"]
# 5000/3200 - 1 = 56%. Not a rounding difference — 56% more building on a number a deal is priced
# from. The direction is the invariant: the rectangle can never understate.
assert rect_run["buildable_gfa_m2"] > poly_run["buildable_gfa_m2"], (rect_run, poly_run)
# ...and the ring really is offset inward, not merely used for its area: the buildable footprint is
# a polygon, and it is smaller than the parcel.
assert poly_run["buildable_polygon"] and len(poly_run["buildable_polygon"]) == 6, poly_run["buildable_polygon"]
assert poly_run["footprint_m2"] < e["area_m2"], poly_run["footprint_m2"]

# A rectangular parcel is the degenerate case: ring and bounding box agree, so nothing changes and
# the panel must not claim an overstatement. Without this the assertions above would also pass for
# an `analyze` that returned the BBOX corners as the ring.
sq = pg.analyze(geojson=rect)
assert sq["bounding_rect_m2"] == sq["area_m2"] == 5000.0, sq
assert sq["lot_width_m"] == 100.0 and sq["lot_depth_m"] == 50.0, sq

# A lon/lat ring returns `ring_m` in METRES, not degrees — the field is what `lot_polygon` consumes,
# and a degree-valued ring would silently generate a 1 m building.
lm = pg.analyze(geojson=ll)["ring_m"]
assert 111.0 < max(x for x, _ in lm) < 112.0, lm            # ~111.19 m per 0.001 degree
assert lm[0] == [0.0, 0.0], lm

# --- bad input raises ------------------------------------------------------------------------------
for bad in ({"type": "Point", "coordinates": [0, 0]}, "not json {", None):
    try:
        pg.analyze(geojson=bad)
        raise AssertionError(f"expected ValueError for {bad!r}")
    except (ValueError, TypeError, KeyError):
        pass

# --- route: 422 on a bad boundary; 200 otherwise ---------------------------------------------------
if os.path.exists("./test_parcel_geometry.db"):
    os.remove("./test_parcel_geometry.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/parcels/analyze", json={"geojson": {"type": "Point", "coordinates": [0, 0]}}).status_code == 422
    # PARCEL-SHAPE end to end, over HTTP. The section above proves the two ENGINES disagree; this
    # proves the ring survives the wire — `MassingIn.lot_polygon` accepts the exact shape
    # `/parcels/analyze` emits. Calling `compute_massing` directly skips that validation entirely,
    # which is the half a schema change would break silently.
    ar = c.post("/parcels/analyze", json={"geojson": ell})
    assert ar.status_code == 200, ar.text
    aj = ar.json()
    env = {"far": 2.0, "side_setback": 5, "front_setback": 5, "rear_setback": 5}
    pv = c.post("/generate/massing/preview", json={**env, "lot_polygon": aj["ring_m"]})
    rc = c.post("/generate/massing/preview",
                json={**env, "lot_width": aj["lot_width_m"], "lot_depth": aj["lot_depth_m"]})
    assert pv.status_code == 200 and rc.status_code == 200, (pv.text, rc.text)
    pm, rm = pv.json()["metrics"], rc.json()["metrics"]
    assert pm["lot_area_m2"] == 1600.0 and rm["lot_area_m2"] == 2500.0, (pm, rm)
    assert pm["buildable_gfa_m2"] == 3200.0 and rm["buildable_gfa_m2"] == 5000.0, (pm, rm)
    # And the proforma seeded from each carries the bias forward, which is the point of the item:
    # the rectangle's deal is underwritten on a building that does not fit on the lot.
    assert pv.json()["proforma"] != rc.json()["proforma"], "the two runs must not seed the same deal"

    rr = c.post("/parcels/analyze", json={"geojson": rect, "zoning": {"max_far": 2.0},
                                          "proposal": {"gfa_m2": 12_000}})
    assert rr.status_code == 200, rr.text
    assert rr.json()["compliance"]["violations"] == ["FAR"], rr.json()

print("PARCEL-IMPORT OK - a 100x50 m parcel parses from GeoJSON/Feature/WKT to exactly 5,000 m² (1.236 ac, "
      "300 m perimeter); a lon/lat ring projects equirectangularly to within 1% of the analytic area; against "
      "a max-FAR 2.0 / coverage 0.6 / height 30 m envelope a 12,000 m² GFA proposal is FAR 2.4 (violation, "
      "max buildable 10,000 m²) while coverage 0.4 and height-at-limit pass; missing limits report ok=None; "
      "the /parcels/analyze route 422s on a Point and returns the compliance read otherwise. "
      "PARCEL-SHAPE: `ring_m` comes back in metres, open and origin-shifted, and an L-shaped 1,600 m² "
      "lot inside a 50x50 m box yields 3,200 m² GFA through `lot_polygon` against 5,000 m² through the "
      "bounding rectangle - 56% more building on the number a deal is priced from.")
