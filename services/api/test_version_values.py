"""VERSION-COMPARE (values) — the per-property VALUE snapshot: a diff now reports `2HR -> 1HR`,
not just "FireRating changed"; the caps are honest; and adding the value cache can't inflate the
modified count on the first snapshot after the upgrade.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_version_values.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_version_values.db"
os.environ["STORAGE_DIR"] = "./test_storage_vervals"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_version_values.db"):
    os.remove("./test_version_values.db")

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import versions  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app):                       # boot once so the schema exists for the direct sessions
    pass

# --- the value snapshot itself: caps are deterministic, containers summarized -----------------------
vals = versions._prop_values({"Pset_A": {"Rating": "2HR", "Load": 4.5, "id": 99}}, None)
assert vals == {"Pset_A.Rating": "2HR", "Pset_A.Load": "4.5"}, vals      # `id` bookkeeping dropped
assert versions._clip("x" * 200).endswith("…") and len(versions._clip("x" * 200)) == 64
assert versions._clip([1, 2, 3]) == "[3 values]" and versions._clip({"a": 1}) == "{1 keys}"
wide = {"Pset_W": {f"P{i:03d}": i for i in range(100)}}
capped = versions._prop_values(wide, None)
assert len(capped) == versions._MAX_VALUE_PROPS                          # capped…
assert capped == versions._prop_values(wide, None)                       # …deterministically (sorted)

# --- a real two-version diff carries from/to -------------------------------------------------------
PID = "p-vv"


def idx(rating: str, extra: dict | None = None) -> dict:
    psets = {"Pset_WallCommon": {"FireRating": rating, "IsExternal": True}}
    if extra:
        psets["Pset_WallCommon"].update(extra)
    return {"elements": [
        {"guid": "G-WALL-1", "name": "Wall A", "ifc_class": "IfcWall", "type_name": None,
         "storey": "Level 1", "psets": psets, "qtos": {"Qto_WallBaseQuantities": {"Length": 8.0}}},
        {"guid": "G-SLAB-1", "name": "Slab", "ifc_class": "IfcSlab", "type_name": None,
         "storey": "Level 1", "psets": {}, "qtos": {}},
    ]}


v1 = versions.snapshot(PID, idx("2HR"))
assert v1["version"] == 1
v2 = versions.snapshot(PID, idx("1HR", {"AcousticRating": "STC50"}))
assert v2["version"] == 2 and v2["modified"] == 1, v2                    # only the wall moved

with SessionLocal() as db:
    d = versions.diff(db, PID, 1, 2)
assert d["property_values_available"] and not d["values_truncated"], d
assert d["modified_count"] == 1 and d["unchanged_count"] == 1
props = {p["property"]: p for p in d["modified"][0]["changed_properties"]}
assert props["Pset_WallCommon.FireRating"] == {
    "property": "Pset_WallCommon.FireRating", "status": "changed", "from": "2HR", "to": "1HR"}, props
added = props["Pset_WallCommon.AcousticRating"]
assert added["status"] == "added" and added["from"] is None and added["to"] == "STC50", added
assert "properties changed" in d["modified"][0]["changes"]

# a no-op republish is still skipped (values don't make an identical model look modified)
assert versions.snapshot(PID, idx("1HR", {"AcousticRating": "STC50"})).get("skipped")

# --- upgrade safety: a pre-values version (positions 0..6 only) doesn't read as all-modified -------
old_fp = ["Wall A", "IfcWall", None, "Level 1", "h1", "h2", {"Pset_WallCommon.FireRating": "hash"}]
new_fp = [*old_fp, {"Pset_WallCommon.FireRating": "2HR"}]               # same meaning + value cache
assert not versions._materially_differs(old_fp, new_fp)
assert versions._materially_differs(old_fp, ["Wall B", *old_fp[1:]])    # a real rename still counts

print("VERSION-VALUES OK - the bounded value snapshot rides fingerprint position [7]: a diff now "
      "reports FireRating 2HR -> 1HR and names an added AcousticRating (from=None, to=STC50) "
      "instead of only saying 'properties changed'; values are capped deterministically (40 sorted "
      "keys/element, 64-char clip, containers summarized) and the id bookkeeping key is dropped; a "
      "no-op republish is still skipped; and a version predating the cache does NOT read as "
      "modified (positions 0..6 decide meaning) while a genuine rename still does.")
