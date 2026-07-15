"""W11 G1 LOD-500 as-built verification: verify_asbuilt stamps the field-verified reliability attribute
(BIMForum's actual LOD 500 definition) and asbuilt_summary reports readiness by method.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_lod500.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_lod500_test.ifc")
massing.generate_blank_ifc(TMP, name="LOD500 Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
walls = [edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st),
         edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st),
         edit.add_wall(m, [6, 4], [0, 4], 3.0, 0.2, st),
         edit.add_wall(m, [0, 4], [0, 0], 3.0, 0.2, st)]

# nothing verified yet → 0% readiness
s0 = edit.asbuilt_summary(m)
assert s0["verified"] == 0 and s0["readiness_pct"] == 0.0, s0
assert s0["total"] >= 4, s0  # 4 walls + the ground slab

# verify two of the four walls by laser scan
n = edit.verify_asbuilt(m, walls[:2], verified_by="J. Field", method="laser-scan", note="scan-to-BIM")
assert n == 2, n
s1 = edit.asbuilt_summary(m)
assert s1["verified"] == 2, s1
assert s1["by_method"].get("laser-scan") == 2, s1["by_method"]
assert 0 < s1["readiness_pct"] < 100, s1

# the stamp is a real, round-trippable Pset with provenance
ps = ue.get_pset(m.by_guid(walls[0]), "Massing_AsBuilt") or {}
assert ps.get("Status") == "VERIFIED" and ps.get("VerifiedBy") == "J. Field", ps
assert ps.get("Method") == "laser-scan" and ps.get("VerifiedDate"), ps
assert ps.get("Note") == "scan-to-BIM", ps

# an unknown method falls back to a valid default; a bad GUID never aborts the batch
n2 = edit.verify_asbuilt(m, [walls[2], "NOTAGUID"], method="bogus")
assert n2 == 1, n2
ps2 = ue.get_pset(m.by_guid(walls[2]), "Massing_AsBuilt") or {}
assert ps2.get("Method") == "field-measure", ps2  # bogus → default

# via the registered recipe lambda (the POST /edit dispatch path) with an explicit date
edit.RECIPES["verify_asbuilt"](m, {"guids": [walls[3]], "method": "inspection", "date": "2026-07-14"})
ps3 = ue.get_pset(m.by_guid(walls[3]), "Massing_AsBuilt") or {}
assert ps3.get("Method") == "inspection" and ps3.get("VerifiedDate") == "2026-07-14", ps3

s2 = edit.asbuilt_summary(m)
assert s2["verified"] == 4, s2  # 2 laser + 1 field-measure + 1 inspection

# --- G3: manufacturer / serial info for the O&M / turnover layer ------------------------------------
assert s2["with_manufacturer"] == 0 and s2["with_serial"] == 0, s2   # nothing stamped yet
n = edit.set_manufacturer_info(m, [walls[0], walls[1]], manufacturer="Acme Walls",
                               model_label="AW-200", production_year="2026", serial="SN-0001")
assert n == 2, n
# only non-empty fields get written; a bad GUID doesn't abort the batch
assert edit.set_manufacturer_info(m, ["not-a-guid", walls[2]], manufacturer="Beta Co") == 1
w0 = ue.get_pset(m.by_guid(walls[0]), "Pset_ManufacturerTypeInformation") or {}
assert w0.get("Manufacturer") == "Acme Walls" and w0.get("ModelLabel") == "AW-200", w0
occ = ue.get_pset(m.by_guid(walls[0]), "Pset_ManufacturerOccurrence") or {}
assert occ.get("SerialNumber") == "SN-0001", occ
# a call with no non-empty fields stamps nothing
assert edit.set_manufacturer_info(m, [walls[3]]) == 0

s3 = edit.asbuilt_summary(m)
assert s3["with_manufacturer"] == 3 and s3["with_serial"] == 2, s3   # mfr: walls 0,1 + wall 2 (Beta); serial: walls 0,1 (same batch)

# G3 via the recipe registry (apply path through the guards gate — guids required)
from aec_data import guards  # noqa: E402
assert guards.precheck("set_manufacturer_info", {"guids": [], "manufacturer": "X"})["errors"], "empty selection blocked"
assert guards.precheck("set_manufacturer_info", {"guids": [walls[0]], "manufacturer": "X"})["ok"]

if os.path.exists(TMP):
    os.remove(TMP)

print("LOD500 OK - verify_asbuilt stamps Massing_AsBuilt (Status/VerifiedBy/Date/Method/Note), bad method "
      "falls back and bad GUIDs are skipped, asbuilt_summary reports readiness % + by-method counts; G3 "
      "set_manufacturer_info stamps Pset_ManufacturerTypeInformation/Occurrence (non-empty fields only, "
      "bad GUID skipped), and the summary counts with_manufacturer / with_serial.")
