"""Model version history + diff: snapshot GUID sets per publish, list, diff (added/removed).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_versions.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./versions_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_ver"
os.environ.pop("AEC_RBAC", None)
for f in ("./versions_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import versions  # noqa: E402
from aec_api.main import app  # noqa: E402


def idx(*guids):
    return {"elements": [{"guid": g} for g in guids], "counts": {"elements": len(guids)}}


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Versioned"}).json()["id"]

    s1 = versions.snapshot(pid, idx("A", "B", "C"))
    assert s1["version"] == 1 and s1["element_count"] == 3, s1
    s2 = versions.snapshot(pid, idx("B", "C", "D"))            # +D, -A
    assert s2["version"] == 2 and s2["added"] == 1 and s2["removed"] == 1, s2
    # an identical republish is skipped (history stays meaningful)
    s3 = versions.snapshot(pid, idx("B", "C", "D"))
    assert s3.get("skipped"), s3

    hist = c.get(f"/projects/{pid}/versions").json()
    assert [h["version"] for h in hist] == [2, 1], hist     # newest first
    assert hist[0]["element_count"] == 3 and hist[0]["note"] == "+1/-1", hist[0]

    d = c.get(f"/projects/{pid}/versions/diff?a=1&b=2").json()
    assert d["added"] == ["D"] and d["removed"] == ["A"] and d["unchanged_count"] == 2, d
    assert d["modified"] == [] and d["modified_count"] == 0, d      # bare-guid idx → no fingerprint changes

    # --- MODEL-DIFF: element-level modified detection on a richly-fingerprinted index -----------------
    def el(guid, name, cls, typ, storey, psets=None, qtos=None):
        return {"guid": guid, "name": name, "ifc_class": cls, "type_name": typ, "storey": storey,
                "psets": psets or {}, "qtos": qtos or {}}

    pid2 = c.post("/projects", json={"name": "Diffable"}).json()["id"]
    v1 = {"elements": [
        el("W1", "Wall 1", "IfcWall", "Basic-200", "L1", {"Pset_WallCommon": {"FireRating": "1HR"}},
           {"Qto_WallBaseQuantities": {"NetSideArea": 20.0}}),
        el("D1", "Door 1", "IfcDoor", "SGL-900", "L1"),
        el("C1", "Col 1", "IfcColumn", "W12", "L1"),
        el("OLD", "Gone", "IfcSlab", None, "L1"),
    ]}
    r1 = versions.snapshot(pid2, v1)
    assert r1["version"] == 1, r1
    v2 = {"elements": [
        # W1: FireRating changed (properties) + area changed (quantities) → two change labels
        el("W1", "Wall 1", "IfcWall", "Basic-200", "L1", {"Pset_WallCommon": {"FireRating": "2HR"}},
           {"Qto_WallBaseQuantities": {"NetSideArea": 24.0}}),
        el("D1", "Door 1A", "IfcDoor", "DBL-1800", "L2"),   # renamed + retyped + re-leveled
        el("C1", "Col 1", "IfcColumn", "W12", "L1"),        # unchanged
        el("NEW", "New beam", "IfcBeam", "W16", "L1"),      # added
    ]}
    r2 = versions.snapshot(pid2, v2)
    assert r2["added"] == 1 and r2["removed"] == 1 and r2["modified"] == 2, r2   # +NEW, -OLD, ~W1,D1
    assert r2["version"] == 2, r2

    dd = c.get(f"/projects/{pid2}/versions/diff?a=1&b=2").json()
    assert dd["added"] == ["NEW"] and dd["removed"] == ["OLD"], dd
    assert dd["modified_available"] is True and dd["modified_count"] == 2, dd
    by = {m["guid"]: m for m in dd["modified"]}
    assert set(by) == {"W1", "D1"}, by
    assert set(by["W1"]["changes"]) == {"properties changed", "quantities changed"}, by["W1"]
    assert set(by["D1"]["changes"]) == {"renamed", "retyped", "moved to another level"}, by["D1"]
    assert by["W1"]["ifc_class"] == "IfcWall" and by["W1"]["name"] == "Wall 1", by["W1"]
    # unchanged_count excludes the modified ones (C1 is the only truly-unchanged common element)
    assert dd["unchanged_count"] == 1, dd
    # a genuine no-op republish (identical fingerprints) is skipped
    assert versions.snapshot(pid2, v2).get("skipped"), "identical republish skipped"

    print("VERSIONS OK - snapshot per publish (A,B,C -> B,C,D), no-op skipped, history newest-first, diff "
          "+D/-A; MODEL-DIFF detects element-level modifications on GUID-stable elements: W1 (properties + "
          "quantities changed), D1 (renamed + retyped + re-leveled), +NEW/-OLD, C1 unchanged — with the "
          "change labels, and an identical-fingerprint republish still skipped.")
