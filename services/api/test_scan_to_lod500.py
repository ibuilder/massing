"""Scan → LOD 500: the step that makes field verification affordable.

Getting a model to LOD 500 meant asserting verification element by element, by hand, across thousands
of elements. Nobody does that, so LOD 500 stays aspirational. A laser scan already contains the
evidence — what was missing was the ability to *attribute* it.

`analyze` compares a cloud to the whole model and returns one aggregate. That answers "how close is
this building to its model" and can never answer "is this wall where we drew it", so it cannot verify
anything. `per_element_deviation` runs the query the other way — nearest SCAN point to each element's
own vertices — which is what makes attribution possible, and what makes an unscanned element show up
as *unseen* rather than as *fine*.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_scan_to_lod500.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_scan_to_lod500.db"
os.environ["STORAGE_DIR"] = "./test_storage_scan_lod500"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_scan_to_lod500.db"):
    os.remove("./test_scan_to_lod500.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import numpy as np  # noqa: E402

from aec_api import lod  # noqa: E402
from aec_api import scan_deviation as sd
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "_scan_lod500.ifc")
massing.generate_blank_ifc(PATH, name="Scan LOD500", storeys=1, storey_height=3.5, ground_size=30.0)
model = open_model(PATH)
storey = model.by_type("IfcBuildingStorey")[0].Name
# three walls: one we will scan accurately, one we will scan and find displaced, one we never scan
g_good = edit.add_wall(model, [0, 0], [8, 0], 3.0, 0.2, storey)
g_off = edit.add_wall(model, [0, 6], [8, 6], 3.0, 0.2, storey)
g_unseen = edit.add_wall(model, [0, 20], [8, 20], 3.0, 0.2, storey)
for g in (g_good, g_off, g_unseen):
    assert isinstance(g, str) and len(g) == 22, g

TOL = 0.05


def shell_cloud(x0, x1, y0, y1, z0, z1, step=0.04, offset=0.0):
    """Points on ALL SIX faces of a box — what a complete scan of an element looks like. A sheet over
    one face only is a partial scan, and the engine is right to report the unscanned faces as
    deviation, so the fixture has to be honest about coverage."""
    ax = np.arange(x0, x1 + 1e-9, step)
    ay = np.arange(y0, y1 + 1e-9, step / 3)
    az = np.arange(z0, z1 + 1e-9, step)
    out = []
    for y in (y0, y1):
        gx, gz = np.meshgrid(ax, az)
        out.append(np.column_stack([gx.ravel(), np.full(gx.size, y), gz.ravel()]))
    for x in (x0, x1):
        gy, gz = np.meshgrid(ay, az)
        out.append(np.column_stack([np.full(gy.size, x), gy.ravel(), gz.ravel()]))
    for z in (z0, z1):
        gx, gy = np.meshgrid(ax, ay)
        out.append(np.column_stack([gx.ravel(), gy.ravel(), np.full(gx.size, z)]))
    pts = np.vstack(out)
    pts[:, 1] += offset
    return pts


# scan the first wall accurately and the second one displaced well past tolerance; never scan the third
points = np.vstack([shell_cloud(0, 8, -0.1, 0.1, 0, 3),
                    shell_cloud(0, 8, 5.9, 6.1, 0, 3, offset=0.35)])
dev = sd.per_element_deviation(model, points, tolerance=TOL)
rows = {r["guid"]: r for r in dev["elements"]}
assert g_good in rows and g_off in rows and g_unseen in rows, sorted(rows)[:5]

# ---- attribution: the result is PER ELEMENT, which the aggregate could never be -------------------
assert rows[g_good]["covered"] is True and rows[g_good]["within_tolerance"] is True, rows[g_good]
assert rows[g_off]["covered"] is True and rows[g_off]["within_tolerance"] is False, rows[g_off]
assert rows[g_good]["p95_deviation"] <= TOL < rows[g_off]["p95_deviation"], \
    (rows[g_good]["p95_deviation"], rows[g_off]["p95_deviation"])

# ---- THE HONESTY POINT: an element the scan never saw is UNCOVERED, not passing -------------------
assert rows[g_unseen]["covered"] is False, rows[g_unseen]
assert rows[g_unseen]["within_tolerance"] is None, "no scan coverage must yield no verdict"
assert "not a pass" in (rows[g_unseen].get("note") or ""), rows[g_unseen]
assert dev["uncovered"] >= 1 and dev["covered"] >= 2, (dev["covered"], dev["uncovered"])
assert dev["within_tolerance"] >= 1 and dev["out_of_tolerance"] >= 1, dev

# an empty cloud is refused rather than reported as a model in perfect agreement with nothing
empty = sd.per_element_deviation(model, np.zeros((0, 3)), tolerance=TOL)
assert empty["elements"] == [] and "empty point cloud" in empty["error"]
assert empty["covered"] == 0 and empty["within_tolerance"] == 0

# ---- dry run: see what a scan would assert before it touches the model ---------------------------
plan = sd.verify_from_scan(model, dev, verified_by="Survey Co", apply=False)
assert plan["applied"] is False and plan["stamped"] == 0, plan
assert plan["verified"] >= 1 and plan["findings_count"] >= 1 and plan["uncovered"] >= 1
assert g_unseen in plan["uncovered_guids"], plan["uncovered_guids"][:5]
assert any(f["guid"] == g_off for f in plan["findings"]), plan["findings"]
# a finding carries the number that failed it, so it can be triaged rather than merely listed
bad = next(f for f in plan["findings"] if f["guid"] == g_off)
assert bad["p95_deviation"] > TOL and bad["ifc_class"], bad

# ---- apply: verified elements are stamped WITH their accuracy ------------------------------------
applied = sd.verify_from_scan(model, dev, verified_by="Survey Co", apply=True)
assert applied["applied"] is True
assert applied["stamped"] == applied["verified"] >= 1, applied
assert applied["accuracy_recorded"] == applied["verified"], "every stamp must state its accuracy"

import ifcopenshell.util.element as ue  # noqa: E402

good_el = model.by_guid(g_good)
ab = ue.get_pset(good_el, "Massing_AsBuilt") or {}
assert ab.get("Status") == "VERIFIED" and ab.get("Method") == "laser-scan", ab
assert ab.get("VerifiedBy") == "Survey Co" and ab.get("VerifiedDate"), ab
dims = ue.get_pset(good_el, "Massing_AsBuiltDim") or {}
assert "ScanDeviation_Measured" in dims, dims
assert str(dims.get("WithinTolerance")).lower() in ("true", "1"), dims

# the out-of-tolerance wall is deliberately NOT stamped — verified-as-wrong is a punch item
off_ab = ue.get_pset(model.by_guid(g_off), "Massing_AsBuilt") or {}
assert str(off_ab.get("Status") or "").upper() != "VERIFIED", off_ab
# and neither is the one nobody scanned
unseen_ab = ue.get_pset(model.by_guid(g_unseen), "Massing_AsBuilt") or {}
assert str(unseen_ab.get("Status") or "").upper() != "VERIFIED", unseen_ab

# ---- END TO END: the stamped element now reads LOD 500 through the LOD engine --------------------
def index_entry(el):
    psets = {}
    for name in ("Massing_AsBuilt", "Massing_AsBuiltDim"):
        ps = ue.get_pset(el, name)
        if ps:
            psets[name] = ps
    return {"ifc_class": el.is_a(), "type_name": "W", "classification": "C",
            "psets": psets, "qtos": {"q": 1}}


idx = {g: index_entry(model.by_guid(g)) for g in (g_good, g_off, g_unseen)}
assert lod.achieved_lod(idx[g_good]) == "LOD 500", lod.achieved_lod(idx[g_good])
assert lod.achieved_lod(idx[g_off]) != "LOD 500"
assert lod.achieved_lod(idx[g_unseen]) != "LOD 500"
v = lod.verification(idx[g_good])
assert v["verified"] and v["accuracy_stated"] and v["method"] == "laser-scan", v

ready = lod.handover_readiness(None, "p1", idx)
assert ready["lod500"] == 1 and ready["elements"] == 3, ready
assert {g["reason"] for g in ready["gaps"]} == {"not_verified"}, ready["by_reason"]
assert all(g["guid"] in (g_off, g_unseen) for g in ready["gaps"])

os.remove(PATH)
print("SCAN-TO-LOD500 OK - field verification is now something a scan can do instead of something a "
      "person does element by element, which is why LOD 500 usually stays aspirational on a model of "
      "any size. The existing whole-model deviation compares a cloud to every vertex at once and "
      "returns one number: it can say how close a building is to its model and never which wall is "
      "wrong, so it could not verify anything. Running the query the other way — nearest scan point "
      "to each element's own surface — makes the result attributable, and makes the important case "
      "visible: an element the scanner never saw comes back UNCOVERED with no verdict rather than "
      "quietly passing, because absence of points is not evidence of correctness. Three outcomes, "
      "and the separation is the value: within tolerance gets stamped together with its measured "
      "deviation, so the LOD 500 assertion states an accuracy; outside tolerance is returned as a "
      "finding and deliberately NOT stamped, since verified-as-wrong is a punch item; uncovered "
      "needs another scan position. A dry run shows exactly what a scan would assert before it "
      "touches the model, and the stamped element then reads LOD 500 through the LOD engine "
      "end to end.")
