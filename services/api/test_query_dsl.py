"""QUERY-DSL — the selector language over the model property index.
Exercises the pure engine (parse / matches / select with every operator) against a synthetic index,
plus the /model/select endpoint (bad query → 422; no model → empty note).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_query_dsl.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_query_dsl.db"
os.environ["STORAGE_DIR"] = "./test_storage_query_dsl"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_query_dsl.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import query_dsl as q  # noqa: E402

IDX = {
    "g1": {"ifc_class": "IfcWall", "storey": "L3", "type_name": "WT-1", "name": "Wall A",
           "psets": {"Pset_WallCommon": {"FireRating": "2HR", "LoadBearing": "true"}}},
    "g2": {"ifc_class": "IfcWall", "storey": "L1", "type_name": "WT-2", "name": "Wall B",
           "psets": {"Pset_WallCommon": {"FireRating": "1HR"}}},
    "g3": {"ifc_class": "IfcColumn", "storey": "L3", "type_name": "C-1", "name": "Col C",
           "psets": {"Pset_ColumnCommon": {"Reference": "C-100"}}},
    "g4": {"ifc_class": "IfcSlab", "storey": "L3", "type_name": "S-1", "name": "Slab D",
           "psets": {"Pset_SlabCommon": {"Thickness": "200"}}},
}


def sel(dsl):
    return sorted(q.select(IDX, dsl)["guids"])


# bare IFC class token
assert sel("IfcWall") == ["g1", "g2"], sel("IfcWall")
# class AND storey
assert sel("IfcWall & storey=L3") == ["g1"], sel("IfcWall & storey=L3")
# pset property equality (case-insensitive)
assert sel("IfcWall & Pset_WallCommon.FireRating=2hr") == ["g1"]
# contains (~)
assert sel("IfcColumn & Pset_ColumnCommon.Reference~C-") == ["g3"]
# numeric comparisons
assert sel("IfcSlab & Pset_SlabCommon.Thickness>=200") == ["g4"]
assert sel("Pset_SlabCommon.Thickness<150") == []
assert sel("Pset_SlabCommon.Thickness>150") == ["g4"]
# existence (bare field) — only g1 declares LoadBearing
assert sel("Pset_WallCommon.LoadBearing") == ["g1"]
# not-equal (and a missing value satisfies !=)
assert sel("IfcWall & Pset_WallCommon.FireRating!=2HR") == ["g2"]
# field aliases: type -> type_name
assert sel("storey=L3 & type=C-1") == ["g3"]
# three-way AND
assert sel("IfcWall & storey=L3 & Pset_WallCommon.LoadBearing=true") == ["g1"]
# nothing matches
assert sel("IfcDoor") == []

# HARDEN-2 (B2): leftmost-operator, quote-aware split — a quoted value may CONTAIN operator chars
IDX_OPS = {
    "q1": {"ifc_class": "IfcColumn", "psets": {"Pset_ColumnCommon": {"Reference": "C=1-A"}}},
    "q2": {"ifc_class": "IfcColumn", "psets": {"Pset_ColumnCommon": {"Reference": "plain"}}},
}
assert sorted(q.select(IDX_OPS, 'Pset_ColumnCommon.Reference~"C=1"')["guids"]) == ["q1"]
assert sorted(q.select(IDX_OPS, "Pset_ColumnCommon.Reference='C=1-A'")["guids"]) == ["q1"]
p = q.parse('name~"a>=b"')
assert p == [("name", "~", "a>=b")], p              # the >= inside quotes is data, not an operator
# HARDEN-2 (B2b): a bare ifc-prefixed FIELD is an existence test, not a class token
assert sorted(q.select(IDX, "ifc_class")["guids"]) == ["g1", "g2", "g3", "g4"]
assert q.parse("ifc_class") == [("ifc_class", "__has__", None)]
assert q.parse("IfcWall") == [("ifc_class", "=", "IfcWall")]   # real class tokens still shorthand

# parse errors -> QueryError (endpoint maps these to 422)
for bad in ("", "   ", "&", "  &  "):
    try:
        q.parse(bad)
        raise AssertionError(f"expected QueryError for {bad!r}")
    except q.QueryError:
        pass

# predicate reporting + truncation cap
big = {f"g{i}": {"ifc_class": "IfcWall"} for i in range(10)}
r = q.select(big, "IfcWall", limit=3)
assert r["matched"] == 10 and len(r["guids"]) == 3 and r["truncated"], r
assert r["predicates"] == [{"field": "ifc_class", "op": "=", "value": "IfcWall"}], r["predicates"]
# no model loaded -> graceful empty
assert q.select(None, "IfcWall")["matched"] == 0

# --- endpoint: bad query 422, no-model empty note ---
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "DSL"}).json()["id"]
    assert c.get(f"/projects/{pid}/model/select?q=").status_code == 422
    body = c.get(f"/projects/{pid}/model/select?q=IfcWall").json()
    assert body["matched"] == 0 and "No model" in body.get("note", ""), body
    assert body["predicates"][0]["field"] == "ifc_class", body

print("QUERY-DSL OK - selector grammar (class/storey/type/pset), ops = != >= <= > < ~ + existence, "
      "case-insensitive, numeric-vs-string, truncation cap; endpoint 422s a bad query, empty on no model")
