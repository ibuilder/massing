"""Property-scan perf plumbing: gzip-on-the-wire for large color-by, the ids=false compact mode, and the
Redis-backed scan cache's fail-open behaviour.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scan_cache.py"""
import gzip
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scan_cache.db"
os.environ["STORAGE_DIR"] = "./test_storage_scan_cache"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_REDIS_URL", None)          # exercise the in-process path
for _f in ("./test_scan_cache.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.routers import properties as P  # noqa: E402

# --- _gzip_json: small -> plain JSON; large -> gzip on the wire, round-trips ----------------------
small = P._gzip_json({"a": 1})
assert small.headers.get("content-encoding") is None and json.loads(small.body) == {"a": 1}, small.headers
big = {"guids": [f"guid-{i:06d}" for i in range(20000)]}          # well over the 48 KB threshold
gz = P._gzip_json(big)
assert gz.headers.get("content-encoding") == "gzip", gz.headers
assert json.loads(gzip.decompress(gz.body)) == big, "gzip payload must round-trip"
assert len(gz.body) < len(json.dumps(big)), "gzip must be smaller than the raw JSON"

# --- _scan_cached: Redis fail-open — a broken client must not break the scan --------------------
class _BrokenRedis:
    def get(self, *a, **k):
        raise RuntimeError("redis down")

    def setex(self, *a, **k):
        raise RuntimeError("redis down")


_saved = P._scan_redis
P._scan_redis = _BrokenRedis()
calls = {"n": 0}
def _compute():
    calls["n"] += 1
    return {"ok": True, "n": calls["n"]}
r1 = P._scan_cached("proj-x", "k", _compute)             # redis get raises -> compute + in-process cache
r2 = P._scan_cached("proj-x", "k", _compute)             # served from in-process cache (redis setex raised)
assert r1 == {"ok": True, "n": 1} and r2 == {"ok": True, "n": 1}, (r1, r2)
assert calls["n"] == 1, "second call must hit the in-process cache, not recompute"
P._scan_redis = _saved

# --- endpoints: color-by ids=true (guids) vs ids=false (compact distribution) ---------------------
PROPS = {"schema": "IFC4", "elements": [
    {"guid": f"g{i}", "ifc_class": "IfcWall" if i % 2 else "IfcColumn", "storey": "L1", "name": f"E{i}"}
    for i in range(6)]}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    c.post(f"/projects/{pid}/properties/index",
           files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    full = c.get(f"/projects/{pid}/elements/color-by", params={"prop": "ifc_class"}).json()
    assert full["buckets"] and "guids" in full["buckets"][0], "default mode carries GUIDs"
    compact = c.get(f"/projects/{pid}/elements/color-by", params={"prop": "ifc_class", "ids": "false"}).json()
    assert compact["buckets"] and "guids" not in compact["buckets"][0], "ids=false omits GUIDs"
    assert {b["label"]: b["count"] for b in compact["buckets"]} == {"IfcWall": 3, "IfcColumn": 3}, compact
    # a re-request is served from cache (same model version) — still correct
    assert c.get(f"/projects/{pid}/elements/color-by", params={"prop": "ifc_class"}).json()["colored"] == 6

print("SCAN CACHE OK - _gzip_json: small=plain, large=gzip (round-trips, smaller); _scan_cached Redis "
      "fail-open (broken client -> in-process, no recompute on 2nd call); color-by ids=true carries GUIDs, "
      "ids=false is compact label+count (IfcWall=3, IfcColumn=3); cached re-request correct")
