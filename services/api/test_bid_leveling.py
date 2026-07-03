"""Bid leveling — deterministic (offline) apples-to-apples comparison of bid_submission records:
base-bid stats + outliers, scope matrix, scope-gap detection, scope-adjusted low recommendation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_bid_leveling.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_bid_leveling.db"
os.environ["STORAGE_DIR"] = "./test_storage_bid_leveling"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ANTHROPIC_API_KEY", None)          # deterministic path
for _f in ("./test_bid_leveling.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api import bid_leveling                       # noqa: E402
from aec_api.main import app                          # noqa: E402

# --- engine unit test ---
bids = [
    {"data": {"bidder": "Ace Mechanical", "base_bid": 480000, "bond_provided": True,
              "inclusions": ["Ductwork", "Furnish and install VAV boxes"], "exclusions": ["Controls"]}},
    {"data": {"bidder": "Best HVAC", "base_bid": 455000,
              "inclusions": ["Ductwork"], "exclusions": ["Controls", "VAV boxes"]}},
    {"data": {"bidder": "Cut-Rate Air", "base_bid": 300000,          # outlier low, missing scope
              "inclusions": ["Ductwork"], "exclusions": ["Controls", "VAV boxes", "Test and balance"]}},
]
res = bid_leveling.level(bids)
assert res["source"] == "rules", res
assert res["base_stats"]["low"] == 300000 and res["base_stats"]["high"] == 480000, res["base_stats"]
assert "Cut-Rate Air" in res["outliers"], res["outliers"]      # >25% below median -> outlier
# VAV boxes is a scope gap: included by Ace, excluded by the others
gap_items = {g["item"] for g in res["gaps"]}
assert any("vav" in i for i in gap_items), gap_items
# recommendation flags the apparent-low as missing scope others carry
rec = res["recommendation"]
assert rec["apparent_low"] == "Cut-Rate Air" and rec["is_outlier"] and rec["missing_scope"], rec

# empty -> clean message, no fabrication
assert bid_leveling.level([])["vendors"] == []

# --- endpoint ---
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    pkg = c.post(f"/projects/{pid}/modules/bid_package",
                 json={"data": {"name": "HVAC", "trade": "Mechanical"}}).json()
    pkg_id = pkg["id"]
    for b in bids:
        d = dict(b["data"]); d["package"] = pkg_id
        assert c.post(f"/projects/{pid}/modules/bid_submission", json={"data": d}).status_code == 201
    r = c.get(f"/projects/{pid}/bids/leveling/{pkg_id}")
    assert r.status_code == 200, r.text[:200]
    j = r.json()
    assert j["package"] and len(j["vendors"]) == 3, j
    assert j["recommendation"]["apparent_low"] == "Cut-Rate Air", j["recommendation"]
    # the existing summary endpoint still works (not shadowed by the new /{package_rid} route)
    assert c.get(f"/projects/{pid}/bids/leveling").status_code == 200

print("BID LEVELING OK - base stats + >25% outlier flag; scope matrix + gap detection (VAV boxes); "
      "scope-adjusted recommendation flags low bidder missing scope; endpoint 200; summary route intact")
