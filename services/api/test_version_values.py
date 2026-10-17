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

# --- VERSION-VALUES (screen): the TRUE branch of `values_truncated` ---------------------------------
# `apps/web/src/viewer/tools/versionDiffRead.ts` branches on this flag and renders a changed
# property with no values as "(changed, values not stored)", which is a THIRD state beside
# "2HR -> 1HR" and "no snapshot at all". Nothing exercised the flag being True, so the branch the
# screen reads was asserted nowhere — *a flag tested only in its false state is a flag with one
# tested state.*
WIDE_PID = "p-vv-wide"


def wide_idx(shift: int) -> dict:
    # 60 properties, past the 40-key cap, so the sorted TAIL has hashes but no stored value. The
    # hash of a tail key still changes, so the diff names it and can say nothing about the values.
    return {"elements": [
        {"guid": "G-W", "name": "Wide", "ifc_class": "IfcWall", "type_name": None,
         "storey": "L1", "psets": {"Pset_W": {f"P{i:03d}": f"v{i + shift}" for i in range(60)}},
         "qtos": {}},
    ]}


assert versions.snapshot(WIDE_PID, wide_idx(0))["version"] == 1
assert versions.snapshot(WIDE_PID, wide_idx(1))["version"] == 2
with SessionLocal() as db:
    wd = versions.diff(db, WIDE_PID, 1, 2)
assert wd["property_values_available"] and wd["values_truncated"], wd
wprops = {p["property"]: p for p in wd["modified"][0]["changed_properties"]}
# the first 40 sorted keys carry values; a key past the cap carries the change and neither value
assert wprops["Pset_W.P000"]["from"] == "v0" and wprops["Pset_W.P000"]["to"] == "v1", wprops["Pset_W.P000"]
tail = wprops["Pset_W.P059"]
assert tail["status"] == "changed" and tail["from"] is None and tail["to"] is None, tail

# and the OTHER flag's false branch, which the screen renders as "NAMES only": a version whose
# fingerprints predate position [7] has hashes and no values.
with SessionLocal() as db:
    from aec_api.models import ModelVersion
    _v1 = db.query(ModelVersion).filter(ModelVersion.project_id == WIDE_PID,
                                        ModelVersion.version == 1).first()
    _fp = dict(_v1.fingerprints or {})
    _fp["G-W"] = list(_fp["G-W"])[:7]                  # drop the value snapshot, keep the hashes
    _v1.fingerprints = _fp
    db.commit()
with SessionLocal() as db:
    nd = versions.diff(db, WIDE_PID, 1, 2)
assert nd["property_detail_available"] and not nd["property_values_available"], nd
assert not nd["values_truncated"], nd                  # not capped — never stored, a different fact

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
      "modified (positions 0..6 decide meaning) while a genuine rename still does. VERSION-VALUES "
      "adds the two branches a SCREEN reads: `values_truncated` TRUE on a 60-property element, "
      "where a key past the 40 cap carries the change and neither value; and "
      "`property_values_available` FALSE with `values_truncated` FALSE on fingerprints that predate "
      "position [7] -- never stored is a different fact from capped, and the compare card names "
      "them differently.")
