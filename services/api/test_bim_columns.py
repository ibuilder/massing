"""Columnar/interned BIM data layer (G1): string interning + EAV param table + pyarrow aggregate +
Parquet export. Ara3D BimOpenSchema-inspired efficiency.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bim_columns.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bim_columns.db"
os.environ["STORAGE_DIR"] = "./test_storage_bim_columns"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_bim_columns.db",):
    if os.path.exists(_f):
        os.remove(_f)

import pyarrow.parquet as pq  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bim_columns  # noqa: E402
from aec_api.main import app  # noqa: E402

# 4 walls sharing the SAME pset keys/values -> interning should dedup hard
IDX = {f"g{i}": {"ifc_class": "IfcWall", "type_name": "Basic Wall", "name": f"Wall-{i}", "storey": "L1",
                 "psets": {"Pset_WallCommon": {"IsExternal": True, "FireRating": "60"}},
                 "qtos": {"Qto_WallBaseQuantities": {"NetVolume": 5.0}}}
       for i in range(4)}
IDX["c1"] = {"ifc_class": "IfcColumn", "type_name": "Basic Wall", "name": "C1", "storey": "L1"}

# --- build + interning ----------------------------------------------------------------------------
col = bim_columns.build(IDX)
assert col["counts"]["elements"] == 5, col["counts"]
# "Basic Wall" appears 5x, "L1" 5x, "IfcWall" 4x… but each is stored once in the string table
assert col["strings"].count("Basic Wall") == 1 and col["strings"].count("L1") == 1, "strings interned"
# EAV: 4 walls x (2 pset + 1 qto) = 12 param rows; column has none
assert col["counts"]["params"] == 12, col["counts"]

stats = bim_columns.interning_stats(IDX)
assert stats["model_loaded"] and stats["dedup_ratio"] and stats["dedup_ratio"] > 1.0, stats
assert stats["est_bytes_saved"] > 0 and stats["est_reduction_pct"] > 0, stats
assert bim_columns.interning_stats(None)["model_loaded"] is False

# --- pyarrow aggregate + parquet ------------------------------------------------------------------
agg = bim_columns.aggregate(IDX, "ifc_class")
by = {r["group"]: r["value"] for r in agg["rows"]}
assert by == {"IfcWall": 4, "IfcColumn": 1}, by
agg2 = bim_columns.aggregate(IDX, "discipline")     # IfcWall->Structural, IfcColumn->Structural
assert agg2["matched"] == 5, agg2

tbl = pq.read_table(io.BytesIO(bim_columns.params_parquet(IDX)))
assert tbl.num_rows == 12 and set(tbl.column_names) >= {"guid", "set", "prop", "value_str", "value_num"}, tbl.schema
# the EAV table lets us pull, e.g., all FireRating values
fr = [v for p, v in zip(tbl.column("prop").to_pylist(), tbl.column("value_str").to_pylist(), strict=False)
      if p == "FireRating"]
assert fr == ["60"] * 4, fr

# --- endpoints ------------------------------------------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Col"}).json()["id"]
    # no model -> valid guarded responses
    assert c.get(f"/projects/{pid}/model/columnar/stats").json()["model_loaded"] is False
    agg_resp = c.get(f"/projects/{pid}/model/columnar/aggregate")
    assert agg_resp.status_code == 200 and agg_resp.json()["matched"] == 0, agg_resp.text[:120]
    pq_resp = c.get(f"/projects/{pid}/model/export/params.parquet")
    assert pq_resp.status_code in (200, 503), pq_resp.status_code
    if pq_resp.status_code == 200:
        assert pq_resp.content[:4] == b"PAR1", pq_resp.content[:8]

print(f"BIM COLUMNS OK - interning dedups repeated pset keys/values (ratio {stats['dedup_ratio']}x, "
      f"~{stats['est_reduction_pct']}% smaller); build: 5 elements + 12 EAV param rows; pyarrow aggregate "
      f"(IfcWall=4, IfcColumn=1) no row loop; params Parquet round-trips (12 rows, FireRating pullable); "
      f"endpoints guard no-model + Parquet magic PAR1")
